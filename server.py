"""DABAB backend: serves the ATC panel and the engine's plans, records decisions.

    python server.py            ->  http://localhost:8000

Python standard library only. Needs processed/scenario_<date>/plans.json, made by
`python -m engine.run --date 2026-01-03` (add --llm for Gemini explanations).

  GET  /                      the ATC decision panel (dabab_atc_panel.html)
  GET  /api/scenario?date=    the plans in the shape the panel uses
  POST /api/decision          record approve / modify / reject; on approve, write the
                              hand-off message other systems would receive
"""
import json
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "dabab_data_pipeline" / "dabab_data" / "processed"
DECISIONS = PROCESSED / "decisions"
PANEL = "dabab_atc_panel.html"
PORT = 8000
# panel profile keys -> engine profile ids
PROFILE = {"delay": "min_delay", "fuel": "min_fuel", "div": "min_diversions", "conn": "protect_connections"}
# the 12 arrivals the panel lists (real flights from 3 Jan 2026)
PANEL_FLIGHTS = ["EK 086", "FZ 1016", "EK 533", "EK 569", "EK 068", "FZ 952", "FZ 446",
                 "EK 076", "EK 010", "FZ 756", "LH 638", "BA 105"]
_cache = {}


def plans_json(date: str) -> dict:
    p = PROCESSED / f"scenario_{date}" / "plans.json"
    key = (p, p.stat().st_mtime)          # reload automatically when the engine rewrites it
    if key not in _cache:
        _cache.clear()
        _cache[key] = json.loads(p.read_text(encoding="utf-8"))
    return _cache[key]


def hhmm(iso):
    return iso[11:16] if iso else None


def _plan_conf(pr: dict, plan_id: str) -> tuple:
    """(pct, wins) for one plan; older plans.json without per_plan falls back to the profile figure."""
    c = pr["confidence"]
    if "per_plan" in c:
        return c["per_plan"][plan_id]["pct"], c["per_plan"][plan_id]["wins"]
    return (c["pct"], c["agree"]) if plan_id == pr["recommended"] else (0, 0)


def panel_plan(pl: dict, st: dict, d: dict) -> dict:
    """One plan card in the panel's own shape."""
    m, e = pl["metrics"], pl["explanation"]
    byflight = {f["flight"]: f for f in pl["flights"]}
    acts = []
    for fn in PANEL_FLIGHTS:
        f = byflight.get(fn)
        if f is None:
            acts.append(0)
        elif f["action"] == "land":
            acts.append(f["hold_min"])
        else:
            acts.append(f["divert_to_iata"] or "DIV")
    # reliability = share of this plan's landings with at least 15 min of fuel to spare
    landed = max(1, d["scenario"]["flights"] - m["diversions"])
    rel = round(100 * (landed - m["low_margin_landings"]) / landed)
    name = pl.get("card_name", {"en": pl["label"], "ar": pl["label_ar"]})
    return {
        "name": name,
        "delay": round(m["avg_delay_min"]), "div": m["diversions"], "conf": m["stand_changes"],
        "fuel": round(m["fuel_t"]), "co2": round(m["co2_t"]), "conn": m["connecting_pax_at_risk"],
        "risk": round(m["risk_index"], 1),
        # reliability: share of stress tests in which this plan's key result holds
        "rel": rel, "cf": rel, "cfTxt": f"{rel}%",
        "acts": acts, "conflict": [],
        "dvAll": {ap["iata"]: m["diversions_by_airport"].get(ap["icao"], 0) for ap in d["airports"]},
        "why": {L: e[L]["why"] for L in ("en", "ar")},
        "cost": {L: e[L]["cost"] for L in ("en", "ar")},
        "not": {L: e[L]["why_not"] for L in ("en", "ar")},
        "source": pl.get("explanation_source", "template"),
    }


def panel_data(date: str) -> dict:
    """The engine output reshaped to the panel's own constants (PLANS, PROF, DOM, NET)."""
    d = plans_json(date)
    plans, prof = {}, {}
    for key, pid in PROFILE.items():
        pr = next(x for x in d["profiles"] if x["id"] == pid)
        # set 0 = the main plans; set 1 = the alternatives offered after "reject all"
        sets = [pr] + ([pr["alternatives"]] if "alternatives" in pr else [])
        prof[key] = [st["recommended"] for st in sets]
        plans[key] = [{pl["id"]: panel_plan(pl, st, d) for pl in st["plans"]} for st in sets]
    ref = d["reference"]["metrics"]
    a = d.get("alert") or {}
    return {
        "date": date, "plans": plans, "prof": prof,
        "dom": {"delay": round(ref["avg_delay_min"]), "risk": round(ref["risk_index"], 1),
                "div": ref["diversions"], "fuel": round(ref["fuel_t"]), "co2": round(ref["co2_t"]),
                "conn": ref["connecting_pax_at_risk"]},
        "net": [[x["iata"], f"CAT {x['ils_cat']}", 1 if x["usable_in_dense_fog"] else 0,
                 "fog" if (x["min_visibility_m_during_event"] or 9999) < 1000 else ""] for x in d["airports"]],
        "alert": {"watch": hhmm(a.get("watch_start")), "warning": hhmm(a.get("warning_start")),
                  "fog": hhmm(a.get("fog_observed")), "watch_lead_min": a.get("watch_lead_min")},
        "actual": d["actual"]["metrics"],
    }


def handoff(date: str, body: dict) -> dict:
    """The structured message an approved plan produces for downstream systems."""
    d = plans_json(date)
    pid = PROFILE.get(body.get("profile"), "min_fuel")
    pr = next(x for x in d["profiles"] if x["id"] == pid)
    pl = next(x for x in pr["plans"] if x["id"] == body.get("plan"))
    edits = dict(zip(PANEL_FLIGHTS, body.get("acts") or []))
    out = []
    for f in pl["flights"]:
        a = edits.get(f["flight"])
        modified = a is not None and a != (f["hold_min"] if f["action"] == "land" else f["divert_to_iata"])
        if modified:
            act = {"action": "hold_and_land", "hold_min": a} if isinstance(a, (int, float)) else \
                  {"action": "divert", "divert_to": a}
        elif f["action"] == "land":
            act = {"action": "hold_and_land", "ground_delay_min": f["ground_delay_min"],
                   "hold_min": f["hold_min"], "landing": f["landing"], "stand": f["stand"]}
        else:
            act = {"action": "divert", "divert_to": f["divert_to_iata"]}
        out.append({"flight": f["flight"], **act, "modified_by_controller": modified})
    return {
        "message_type": "dabab.decision.v1",
        "issued_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scenario": date, "replay": True,
        "approved_by": body.get("user", "ATC supervisor (demo)"), "human_approved": True,
        "profile": pr["label"], "plan": f"{pl['id']} {pl['label']}",
        "recipients": [
            {"system": "Tower / Approach (arrival manager)", "receives": "landing sequence and holds"},
            {"system": "Airport AODB", "receives": "stand allocations"},
            {"system": "Airline operations centres", "receives": "diversions and ground delays"},
            {"system": "Cockpit (data link)", "receives": "per-flight instruction, pilot accepts or declines"},
        ],
        "instructions": out,
        "note": "Demo: no system receives this message. Format for integration only.",
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT), **k)

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            self.path = "/" + PANEL
            return super().do_GET()
        if u.path == "/api/scenario":
            date = parse_qs(u.query).get("date", ["2026-01-03"])[0]
            try:
                return self._json(panel_data(date))
            except FileNotFoundError:
                return self._json({"error": f"no plans.json for {date}; run python -m engine.run --date {date}"}, 404)
        if u.path.endswith(".html") or u.path.endswith((".jpg", ".png", ".css", ".js")):
            return super().do_GET()
        self.send_error(404)

    def do_POST(self):
        if urlparse(self.path).path != "/api/decision":
            return self.send_error(404)
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        date = body.get("date", "2026-01-03")
        DECISIONS.mkdir(parents=True, exist_ok=True)
        entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **body}
        with open(DECISIONS / "audit_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        res = {"logged": True}
        if body.get("kind") == "approve":
            msg = handoff(date, body)
            name = f"handoff_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            (DECISIONS / name).write_text(json.dumps(msg, ensure_ascii=False, indent=1), encoding="utf-8")
            res.update({"handoff_file": name, "handoff": msg})
        return self._json(res)

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    print(f"DABAB panel: http://localhost:{PORT}   (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
