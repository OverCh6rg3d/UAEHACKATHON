"""Build every plan for one scenario and write plans.json for the dashboard.

    python -m engine.run --date 2026-01-03

For each of the 4 priority profiles: 3 recovery plans (A hold all, B balanced,
C early diversion), a recommendation, a confidence figure from sensitivity runs
and explanations in English and Arabic. Also: what actually happened, and a
no-coordination reference plan in the same simulation.
"""
import argparse
import json

import pandas as pd

from . import config as C
from .explain import IATA, flight_text, plan_text
from .planner import make_plan
from .scenario import load, scaled


def _iso(t):
    return None if t is None or pd.isna(t) else pd.Timestamp(t).isoformat()


def metrics(p: pd.DataFrame) -> dict:
    """Plan metrics from a planner DataFrame."""
    n = len(p)
    diverted = p["action"] != "land"
    landed = p[~diverted]
    burn = p["size_class"].map(C.HOLD_BURN_KG_MIN).fillna(C.HOLD_BURN_KG_MIN["unknown"])
    fuel = float(((p["hold_min"] + p["fly_min"]) * burn).sum())
    d = p["delay_min"].dropna()
    margin = (landed["deadline"] - landed["landing"]).dt.total_seconds() / 60
    low_margin = int((margin < C.RISK_LOW_MARGIN_MIN).sum())
    long_hold = int((p["hold_min"] > C.RISK_LONG_HOLD_MIN).sum())
    w = C.RISK_WEIGHTS
    risk = 100 * (w["low_margin"] * low_margin + w["long_hold"] * long_hold + w["diverted"] * int(diverted.sum())) / n
    by_ap = p.loc[diverted, "divert_to"].fillna("unknown").value_counts().to_dict()
    has_stands = p["new_stand"].notna().any()
    return {
        "avg_delay_min": round(float(d.mean()), 1),
        "median_delay_min": round(float(d.median()), 1),
        "pct_delayed_over_15": round(float((d > 15).mean() * 100), 1),
        "pct_delayed_over_60": round(float((d > 60).mean() * 100), 1),
        "ground_held_flights": int((p["ground_delay_min"] > 0).sum()),
        "total_ground_delay_min": int(p["ground_delay_min"].sum()),
        "total_hold_min": int(p["hold_min"].sum()),
        "max_hold_min": int(p["hold_min"].max()),
        "diversions": int(diverted.sum()),
        "early_diversions": int(p["reason_code"].str.startswith("early").sum()),
        "diversions_by_airport": {str(k): int(v) for k, v in by_ap.items()},
        "unresolved_diversions": int((p["action"] == "divert_unresolved").sum()),
        "fuel_kg": int(round(fuel)), "fuel_t": round(fuel / 1000, 1),
        "co2_t": round(fuel * C.CO2_PER_KG_FUEL / 1000, 1),
        "connecting_pax_at_risk": int(p.loc[(p["delay_min"] > 90) | diverted, "syn_connecting_pax"].sum()),
        "low_margin_landings": low_margin, "long_holds": long_hold,
        "min_fuel_margin_min": int(margin.min()) if len(margin) else None,
        "risk_index": round(risk, 1),
        "stand_conflicts": 0,  # enforced by the stand board
        "stand_changes": int((landed["new_stand"] != landed["stand"]).sum()) if has_stands else None,
        "remote_stands": int((landed["new_stand"] == C.REMOTE_STAND).sum()) if has_stands else None,
    }


def flights_json(p: pd.DataFrame) -> list:
    out = []
    for r in p.itertuples():
        facts = dict(r.facts)
        if isinstance(r.stand_facts, dict):
            facts.update({f"stand_{k}": v for k, v in r.stand_facts.items()})
        f = {
            "id": r.aodbuniquefield, "flight": r.flightnumber, "airline": r.airlinecode_iata,
            "origin": r.origin_iata, "aircraft": r.aircraft_icao, "size_class": r.size_class,
            "eta": _iso(r.eta_normal), "action": r.action,
            "landing": _iso(r.landing), "in_block": _iso(r.in_block),
            "ground_delay_min": int(r.ground_delay_min), "hold_min": int(r.hold_min),
            "delay_min": None if pd.isna(r.delay_min) else int(r.delay_min),
            "fuel_reserve_min_syn": int(r.syn_fuel_reserve_min),
            "stand": r.new_stand, "original_stand": r.stand,
            "stand_changed": bool(r.action == "land" and r.new_stand != r.stand),
            "divert_to": r.divert_to, "divert_to_iata": IATA.get(r.divert_to),
            "priority": r.priority, "reason": {"code": r.reason_code, "facts": facts},
        }
        f["text"] = flight_text(f)
        out.append(f)
    return out


def recommend(plans: dict, objective: str) -> tuple:
    """plans: {id: metrics}. Returns (best id, {id: score}). Lower score is better."""
    def norm(key):
        vals = {k: m[key] for k, m in plans.items()}
        lo, hi = min(vals.values()), max(vals.values())
        return {k: 0.0 if hi == lo else (v - lo) / (hi - lo) for k, v in vals.items()}
    o, r, w = norm(objective), norm("risk_index"), C.RECOMMEND_WEIGHTS
    score = {k: round(w["objective"] * o[k] + w["risk"] * r[k], 3) for k in plans}
    return min(score, key=lambda k: (score[k], plans[k]["fuel_kg"])), score


def confidence(sc, profile_id: str, base_choice: str) -> dict:
    """Share of sensitivity runs (decision lead x fog landing rate) with the same recommendation."""
    cfg, agree, runs = C.PROFILES[profile_id], 0, 0
    for cap in C.SENSITIVITY_CAPACITY:
        s2 = scaled(sc, cap) if cap != 1.0 else sc
        for lead in C.SENSITIVITY_LEADS_MIN:
            ms = {k: metrics(make_plan(s2, cfg["sequence"], k, lead_min=lead, with_stands=False))
                  for k in C.STRATEGIES}
            runs += 1
            agree += recommend(ms, cfg["objective"])[0] == base_choice
    return {"pct": round(100 * agree / runs), "agree": agree, "runs": runs,
            "method": "share of sensitivity runs where this plan stays recommended "
                      f"(decision lead {C.SENSITIVITY_LEADS_MIN} min x fog landing rate {C.SENSITIVITY_CAPACITY})"}


def build_profile(sc, profile_id: str) -> dict:
    cfg = C.PROFILES[profile_id]
    plans = []
    for k, s in C.STRATEGIES.items():
        p = make_plan(sc, cfg["sequence"], k)
        plans.append({"id": k, "key": s["key"], "label": s["label"], "label_ar": s["label_ar"],
                      "metrics": metrics(p), "flights": flights_json(p)})
    best, score = recommend({p["id"]: p["metrics"] for p in plans}, cfg["objective"])
    for p in plans:
        p["recommended"] = p["id"] == best
        p["score"] = score[p["id"]]
        # dominated = another plan is at least as good on delay AND risk, and better on one
        p["dominated"] = any(
            o["metrics"]["avg_delay_min"] <= p["metrics"]["avg_delay_min"]
            and o["metrics"]["risk_index"] <= p["metrics"]["risk_index"]
            and (o["metrics"]["avg_delay_min"], o["metrics"]["risk_index"])
            != (p["metrics"]["avg_delay_min"], p["metrics"]["risk_index"])
            for o in plans if o is not p)
        p["explanation"] = plan_text(p, [o for o in plans if o is not p], profile_id, p["recommended"])
    return {"id": profile_id, "label": cfg["label"], "label_ar": cfg["label_ar"],
            "objective": cfg["objective"], "recommended": best,
            "confidence": confidence(sc, profile_id, best), "plans": plans}


def actual(sc) -> dict:
    """'As it happened', measured with the same definitions where the records allow."""
    f = sc.flights
    d = f["arr_delay_min"].dropna()
    diverted = f["inferred_diverted_or_held"].fillna(False).astype(bool)
    return {
        "label": "As it happened", "label_ar": "ما حدث فعلاً",
        "metrics": {
            "avg_delay_min": round(float(d.mean()), 1),
            "median_delay_min": round(float(d.median()), 1),
            "pct_delayed_over_15": round(float((d > 15).mean() * 100), 1),
            "pct_delayed_over_60": round(float((d > 60).mean() * 100), 1),
            "diversions": int(diverted.sum()),
            "connecting_pax_at_risk": int(f.loc[(f["arr_delay_min"] > 90) | diverted, "syn_connecting_pax"].sum()),
        },
        "notes": ["Diversions are inferred (arrival >= 150 min late), not recorded.",
                  "Holding, fuel and risk are not measurable from the records."],
        "flights": [{"id": r.aodbuniquefield, "flight": r.flightnumber, "origin": r.origin_iata,
                     "aircraft": r.aircraft_icao, "landing": _iso(r.actuallandingtime),
                     "in_block": _iso(r.actualinblocktime), "stand": r.stand,
                     "delay_min": None if pd.isna(r.arr_delay_min) else round(r.arr_delay_min),
                     "inferred_diverted": bool(dv)} for r, dv in zip(f.itertuples(), diverted)],
    }


def airports_block(sc) -> list:
    t0, t1 = pd.Timestamp(sc.summary["fog_start_local"]), pd.Timestamp(sc.summary["fog_end_local"])
    out = []
    for a in sc.airports.itertuples():
        m = sc.metar[(sc.metar["station"] == a.icao) & sc.metar["valid_local"].between(t0, t1)]
        vis = float(m["vis_m"].min()) if not m.empty else None
        out.append({
            "icao": a.icao, "iata": a.iata, "name": a.name, "lat": a.lat, "lon": a.lon,
            "ils_cat": a.ils_cat, "usable_in_dense_fog": a.ils_cat == "III",
            "a380": a.a380, "longest_rwy_m": int(a.longest_rwy_m),
            "km_from_dxb": a.km_from_main, "transfer_min_to_dxb": int(a.est_transfer_min),
            "min_visibility_m_during_event": vis,
            "weather_ok_during_event": None if vis is None else bool(vis >= a.approx_min_rvr_m),
            "diversion_capacity_assumed": C.ALTERNATE_CAPACITY.get(a.icao),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-01-03")
    sc = load(ap.parse_args().date)
    s = sc.summary
    ref = metrics(make_plan(sc, "arrival", "A", ground_delay=False))
    profiles = [build_profile(sc, p) for p in C.PROFILES]
    out = {
        "schema": "dabab.plans.v2",
        "scenario": {
            "date": sc.date, "airport": "OMDB", "replay": True,
            "weather": {"type": "fog", "start": s["fog_start_local"], "end": s["fog_end_local"],
                        "min_visibility_m": s["min_visibility_m"]},
            "decision_lead_min": s.get("decision_lead_min", C.DECISION_LEAD_MIN),
            "decision_time": _iso(pd.Timestamp(s["fog_start_local"])
                                  - pd.Timedelta(minutes=int(s.get("decision_lead_min", C.DECISION_LEAD_MIN)))),
            "capacity_per_hour": {str(h): c for h, c in sorted(sc.capacity.items())},
            "landings_fog_hours": s.get("fog_hour_landings"),
            "landings_normal_same_hours": s.get("normal_landings_same_hours"),
            "flights": int(len(sc.flights)),
        },
        "alert": s.get("alert"),   # fog model: CLEAR / WATCH / WARNING / ALERT timeline and lead times
        "safety_floor": [
            {"en": "Medical and low-fuel flights land first", "ar": "الرحلات الطبية ومنخفضة الوقود تهبط أولاً"},
            {"en": "No landing planned within 5 min of a flight's fuel limit", "ar": "لا هبوط مخططاً ضمن 5 دقائق من حدّ الوقود"},
            {"en": "Diversions only to airports whose weather meets their ILS minima", "ar": "التحويل فقط إلى مطارات يستوفي طقسها حدود نظام الهبوط الآلي"},
            {"en": "Stand must fit the aircraft size; A380 only where accepted", "ar": "الموقف يجب أن يناسب حجم الطائرة؛ A380 حيث تُقبل فقط"},
        ],
        "airports": airports_block(sc),
        "risk_index": {"formula": "100 x (0.5 x flights landing with < 15 min fuel margin + 0.3 x flights holding > 30 min "
                                  "+ 0.2 x diverted flights) / all flights", "note": "Transparent index, not a certified safety metric."},
        "recommendation_rule": "Lowest of 0.6 x profile measure + 0.4 x risk index, each scaled 0-1 across the three plans.",
        "assumptions": [
            "Simplified simulation: results are indicative, not operational predictions.",
            f"Landing capacity in fog hours is what DXB achieved that day; otherwise {C.NORMAL_CAPACITY_PER_H}/h (95th percentile of all hours).",
            f"Each flight's normal-weather ETA = schedule - {C.TAXI_IN_MIN} min taxi + {sc.normal_delay_min:.0f} min normal lateness for this window.",
            "Fuel reserve, connecting passengers and medical priority are synthetic (seeded).",
            f"A diverted flight's delay = {C.DIVERTED_DELAY_MIN} min (median of inferred diversions on 3 Jan 2026).",
            "Holding fuel burn by size class and alternate diversion capacities are planning assumptions.",
            f"Ground delay: decided {s.get('decision_lead_min', C.DECISION_LEAD_MIN)} min before fog onset (never before the fog model's Watch); flights not yet departed wait at origin "
            f"(max {C.GROUND_DELAY_MAX_MIN} min). Flight times are estimated by origin region (ICAO prefix).",
            "Stand sizes from GCAA chart notes or the largest aircraft observed on each stand.",
        ],
        "actual": actual(sc),
        "reference": {"id": "no_coordination", "label": "No coordination", "label_ar": "بدون تنسيق",
                      "goal": "First come, first served, no ground delays, same safety floor.", "metrics": ref},
        "profiles": profiles,
    }
    path = C.PROCESSED / f"scenario_{sc.date}" / "plans.json"
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

    keys = ["avg_delay_min", "diversions", "fuel_t", "connecting_pax_at_risk", "risk_index",
            "low_margin_landings", "max_hold_min", "stand_changes"]
    print(f"{sc.date}  actual: delay {out['actual']['metrics']['avg_delay_min']} "
          f"div {out['actual']['metrics']['diversions']} | no coordination: "
          + ", ".join(f"{k} {ref[k]}" for k in keys[:5]))
    for pr in profiles:
        print(f"\n{pr['label']}  -> recommended {pr['recommended']}  confidence {pr['confidence']['pct']}% "
              f"({pr['confidence']['agree']}/{pr['confidence']['runs']})")
        print(pd.DataFrame({f"{p['id']} {p['label']}" + (" *" if p["recommended"] else ""):
                            {**{k: p["metrics"][k] for k in keys}, "score": p["score"]}
                            for p in pr["plans"]}).to_string())
    print(f"\nWrote {path} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
