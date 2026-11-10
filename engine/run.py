"""Build all plans for one scenario, compare with what happened, write plans.json.

    python -m engine.run --date 2026-01-03
"""
import argparse
import json

import pandas as pd

from . import config as C
from .planner import make_plan
from .scenario import load


def _iso(t):
    return None if t is None or pd.isna(t) else pd.Timestamp(t).isoformat()


def _fuel(df) -> float:
    burn = df["size_class"].map(C.HOLD_BURN_KG_MIN).fillna(C.HOLD_BURN_KG_MIN["unknown"])
    return float(((df["hold_min"] + df.get("fly_min", 0)) * burn).sum())


def _common_metrics(df, diverted_mask) -> dict:
    d = df["delay_min"].dropna()
    fuel = _fuel(df)
    at_risk = df.loc[(df["delay_min"] > 90) | diverted_mask, "syn_connecting_pax"].sum()
    by_ap = df.loc[diverted_mask, "divert_to"].fillna("unknown").value_counts().to_dict() \
        if "divert_to" in df else {}
    return {
        "avg_delay_min": round(float(d.mean()), 1),
        "median_delay_min": round(float(d.median()), 1),
        "pct_delayed_over_15": round(float((d > 15).mean() * 100), 1),
        "pct_delayed_over_60": round(float((d > 60).mean() * 100), 1),
        "total_hold_min": int(df["hold_min"].sum()),
        "max_hold_min": int(df["hold_min"].max()),
        "diversions": int(diverted_mask.sum()),
        "diversions_by_airport": {str(k): int(v) for k, v in by_ap.items()},
        "fuel_kg": int(round(fuel)),
        "co2_t": round(fuel * C.CO2_PER_KG_FUEL / 1000, 1),
        "connecting_pax_at_risk": int(at_risk),
    }


def actual_plan(sc) -> dict:
    """'As it happened', measured with the same definitions as the plans."""
    f = sc.flights.copy()
    f["delay_min"] = f["arr_delay_min"]
    diverted = f["inferred_diverted_or_held"].fillna(False).astype(bool)
    # upper-bound estimate: landing later than the normal-weather ETA, for flights that landed
    f["hold_min"] = ((f["actuallandingtime"] - f["eta"]).dt.total_seconds() / 60).clip(lower=0).fillna(0)
    f.loc[diverted, "hold_min"] = 0
    f["fly_min"] = 0
    m = _common_metrics(f, diverted)
    m.update({"stand_conflicts": None, "stand_changes": 0, "remote_stands": 0,
              "min_fuel_margin_min": None,
              "notes": ["diversions are inferred (arrival >= 150 min late), not recorded",
                        "hold is an upper bound: landing time beyond the normal-weather ETA",
                        "stand conflicts are not measurable from the records (tows are not logged)"]})
    flights = [{
        "id": r.aodbuniquefield, "flight": r.flightnumber, "origin": r.origin_iata,
        "aircraft": r.aircraft_icao, "size_class": r.size_class, "eta": _iso(r.eta),
        "action": "divert" if dv else "land", "landing": _iso(r.actuallandingtime),
        "in_block": _iso(r.actualinblocktime), "hold_min": round(r.hold_min),
        "delay_min": None if pd.isna(r.delay_min) else round(r.delay_min),
        "stand": r.stand, "original_stand": r.stand, "stand_changed": False, "divert_to": None,
        "priority": None, "reason": {"code": "actual", "facts": {}},
    } for r, dv in zip(f.itertuples(), diverted)]
    return {"id": "actual", "label": "As it happened", "goal": "What the data recorded on the day.",
            "is_actual": True, "metrics": m, "flights": flights}


def plan_json(sc, profile: str) -> dict:
    p = make_plan(sc, profile)
    diverted = p["action"] != "land"
    m = _common_metrics(p, diverted)
    landed = p[~diverted]
    m.update({
        "stand_conflicts": 0,  # enforced by the stand board
        "stand_changes": int((landed["new_stand"] != landed["stand"]).sum()),
        "remote_stands": int((landed["new_stand"] == C.REMOTE_STAND).sum()),
        "min_fuel_margin_min": int(((landed["deadline"] - landed["landing"]).dt.total_seconds() / 60).min()),
        "unresolved_diversions": int((p["action"] == "divert_unresolved").sum()),
        "ground_held_flights": int((p["ground_delay_min"] > 0).sum()),
        "total_ground_delay_min": int(p["ground_delay_min"].sum()),
    })
    flights = []
    for r in p.itertuples():
        facts = dict(r.facts)
        if isinstance(r.stand_facts, dict):
            facts.update({f"stand_{k}": v for k, v in r.stand_facts.items()})
        flights.append({
            "id": r.aodbuniquefield, "flight": r.flightnumber, "origin": r.origin_iata,
            "aircraft": r.aircraft_icao, "size_class": r.size_class, "eta": _iso(r.eta_normal),
            "action": r.action, "landing": _iso(r.landing), "in_block": _iso(r.in_block),
            "ground_delay_min": int(r.ground_delay_min),
            "hold_min": int(r.hold_min), "delay_min": None if pd.isna(r.delay_min) else int(r.delay_min),
            "stand": r.new_stand, "original_stand": r.stand,
            "stand_changed": bool(r.action == "land" and r.new_stand != r.stand),
            "divert_to": r.divert_to, "priority": r.priority,
            "reason": {"code": r.reason_code, "facts": facts},
        })
    cfg = C.PROFILES[profile]
    return {"id": profile, "label": cfg["label"], "goal": cfg["goal"], "is_actual": False,
            "metrics": m, "flights": flights}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-01-03")
    sc = load(ap.parse_args().date)
    plans = [actual_plan(sc)] + [plan_json(sc, p) for p in C.PROFILES]
    s = sc.summary
    out = {
        "scenario": {
            "date": sc.date, "airport": "OMDB",
            "weather": {"type": "fog", "start": s["fog_start_local"], "end": s["fog_end_local"],
                        "min_visibility_m": s["min_visibility_m"]},
            "capacity_per_hour": {str(h): c for h, c in sorted(sc.capacity.items())},
            "flights": int(len(sc.flights)),
            "normal_delay_min": round(sc.normal_delay_min, 1),
        },
        "assumptions": [
            "Simplified simulation: results are indicative, not operational predictions.",
            f"Landing capacity in fog hours is what DXB achieved that day; otherwise {C.NORMAL_CAPACITY_PER_H}/h (95th percentile of all hours).",
            f"Each flight's normal-weather ETA = schedule - {C.TAXI_IN_MIN} min taxi + {sc.normal_delay_min:.0f} min normal lateness for this window.",
            "Fuel reserve, connecting passengers and medical priority are synthetic (seeded).",
            f"A diverted flight's delay = {C.DIVERTED_DELAY_MIN} min (median of inferred diversions on 3 Jan 2026).",
            "Holding fuel burn by size class and alternate diversion capacities are planning assumptions.",
            f"Ground delay: decided {C.DECISION_LEAD_MIN} min before fog onset; flights not yet departed wait at origin. "
            "Flight times are estimated by origin region (ICAO prefix).",
            "Stand sizes from GCAA chart notes or the largest aircraft observed on each stand.",
        ],
        "plans": plans,
    }
    path = C.PROCESSED / f"scenario_{sc.date}" / "plans.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False))

    keys = ["avg_delay_min", "pct_delayed_over_60", "ground_held_flights", "total_ground_delay_min",
            "total_hold_min", "max_hold_min", "diversions",
            "fuel_kg", "co2_t", "stand_conflicts", "stand_changes", "remote_stands",
            "connecting_pax_at_risk", "min_fuel_margin_min"]
    tbl = pd.DataFrame({p["label"]: {k: p["metrics"].get(k) for k in keys} for p in plans})
    pd.set_option("display.width", 200)
    print(tbl.to_string())
    for p in plans[1:]:
        print(f"{p['label']}: diversions {p['metrics']['diversions_by_airport']}")
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
