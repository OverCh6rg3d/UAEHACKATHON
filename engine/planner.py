"""Arrival sequencing under reduced capacity, with a hard fuel-safety floor and
ground delay at origin.

Greedy slot allocation: at every landing slot the highest-priority waiting flight
lands. Fast, deterministic and explainable; OR-Tools can replace the choice rule
later without changing the inputs or outputs.

With ground delay on, planning runs in two passes:
  1. Sequence everyone; flights still on the ground at origin at decision time
     have no fuel limit (they are not airborne yet), so they simply get a slot.
  2. Those flights now depart late enough to arrive just before their slot
     (ground delay, no fuel burned); everyone is sequenced again with real limits.
"""
import pandas as pd

from . import config as C
from .diversions import Balancer
from .stands import StandBoard

URGENT_FUEL_MIN = 15  # a flight this close to its fuel limit jumps the queue
SAFETY_BUFFER_MIN = 5  # never plan a landing closer than this to the fuel limit


def _burn(f) -> float:
    return C.HOLD_BURN_KG_MIN.get(f["size_class"], C.HOLD_BURN_KG_MIN["unknown"])


def _profile_key(f, profile: str):
    if profile == "min_diversions":
        return (f["deadline"], f["eta"])
    if profile == "protect_connections":
        return (-f["syn_connecting_pax"], f["eta"])
    if profile == "min_fuel":
        # every slot is the same length, so landing the heaviest burner first
        # minimises total holding fuel
        return (-_burn(f), f["eta"])
    return (f["eta"],)  # arrival_order


def _sequence(sc, flights: list, profile: str, balancer) -> list:
    """One pass of slot allocation. `flights` are dicts with eta and deadline."""
    cfg = C.PROFILES[profile]
    flights = sorted(flights, key=lambda f: f["eta"])
    out, waiting, nxt = [], [], 0
    buf = pd.Timedelta(minutes=SAFETY_BUFFER_MIN)
    slots = [s for s in sc.slots if s >= flights[0]["eta"].floor("h")]

    def divert(f, t, code, extra):
        to, facts = balancer.choose(f, t) if balancer else (None, {})
        hold = max(0.0, (t - f["eta"]).total_seconds() / 60)
        facts.update(extra)
        out.append({**f, "action": "divert" if to or not balancer else "divert_unresolved",
                    "landing": None, "hold_min": round(hold), "divert_to": to,
                    "fly_min": facts.get("fly_min", 0), "priority": "profile",
                    "reason_code": code, "facts": facts})

    for i, t in enumerate(slots):
        while nxt < len(flights) and flights[nxt]["eta"] <= t:
            f = flights[nxt]
            nxt += 1
            limit = cfg["divert_if_hold_over_min"]
            if limit is not None and not f["syn_medical_priority"]:
                projected = slots[min(i + len(waiting), len(slots) - 1)]
                proj_hold = (projected - f["eta"]).total_seconds() / 60
                if proj_hold > limit:
                    divert(f, f["eta"], "early_divert_long_hold",
                           {"projected_hold_min": round(proj_hold), "hold_limit_min": limit})
                    continue
            waiting.append(f)
        # safety: anyone at the fuel limit (minus buffer) must leave for an alternate now
        for f in [w for w in waiting if w["deadline"] - buf < t]:
            waiting.remove(f)
            divert(f, f["deadline"] - buf, "fuel_limit_reached",
                   {"fuel_reserve_min": int(f["syn_fuel_reserve_min"]),
                    "safety_buffer_min": SAFETY_BUFFER_MIN})
        if not waiting:
            if nxt >= len(flights):
                break
            continue

        def rank(f):
            if f["syn_medical_priority"]:
                tier = 0
            elif (f["deadline"] - t).total_seconds() / 60 <= URGENT_FUEL_MIN:
                tier = 1
            else:
                tier = 2
            return (tier,) + _profile_key(f, profile)

        best = min(waiting, key=rank)
        waiting.remove(best)
        tier = rank(best)[0]
        hold = (t - best["eta"]).total_seconds() / 60
        out.append({**best, "action": "land", "landing": t, "hold_min": round(max(0, hold)),
                    "divert_to": None, "fly_min": 0,
                    "priority": ["medical", "low_fuel", "profile"][tier],
                    "reason_code": ["medical_priority", "fuel_priority", f"profile_{profile}"][tier],
                    "facts": {"queue_length_at_landing": len(waiting) + 1,
                              "landing_rate_per_h": sc.capacity.get(t.hour, C.NORMAL_CAPACITY_PER_H),
                              "fuel_margin_min": round((best["deadline"] - t).total_seconds() / 60),
                              "connecting_pax_syn": int(best["syn_connecting_pax"])}})
    return out


def _ground_delay(sc, flights: list, profile: str) -> list:
    """Pass 1 + ETA update for flights still on the ground at decision time."""
    decision = pd.Timestamp(sc.summary["fog_start_local"]) - pd.Timedelta(minutes=C.DECISION_LEAD_MIN)
    for f in flights:
        f["est_flight_min"] = C.est_flight_min(f["origin_icao"])
        f["est_departure"] = f["eta"] - pd.Timedelta(minutes=f["est_flight_min"])
        f["ground_holdable"] = f["est_departure"] >= decision and not f["syn_medical_priority"]
    # on the ground there is no fuel limit, only the ground-delay cap (stops starvation)
    cap = pd.Timedelta(minutes=C.GROUND_DELAY_MAX_MIN)
    trial = [{**f, "deadline": f["deadline"] + cap if f["ground_holdable"] else f["deadline"]}
             for f in flights]
    slot = {r["aodbuniquefield"]: r["landing"] for r in _sequence(sc, trial, profile, None)
            if r["action"] == "land"}
    out = []
    for f in flights:  # noqa: E741 - keep loop short
        f = dict(f)
        f["ground_delay_min"] = 0
        f["eta_normal"] = f["eta"]
        s = slot.get(f["aodbuniquefield"])
        if f["ground_holdable"] and s is not None:
            new_eta = min(max(f["eta"], s - pd.Timedelta(minutes=C.AIRBORNE_BUFFER_MIN)), f["eta"] + cap)
            g = (new_eta - f["eta"]).total_seconds() / 60
            if g > 0:
                f["ground_delay_min"] = round(g)
                f["eta"] = new_eta
                f["deadline"] = new_eta + pd.Timedelta(minutes=float(f["syn_fuel_reserve_min"]))
        out.append(f)
    f_decision = decision
    for f in out:
        f["decision_time"] = f_decision
    return out


def make_plan(sc, profile: str) -> pd.DataFrame:
    cfg = C.PROFILES[profile]
    flights = sc.flights.to_dict("records")
    use_gd = C.GROUND_DELAY and cfg.get("ground_delay", True)
    if use_gd:
        flights = _ground_delay(sc, flights, profile)
    else:
        for f in flights:
            f["ground_delay_min"] = 0
            f["eta_normal"] = f["eta"]
    plan = pd.DataFrame(_sequence(sc, flights, profile, Balancer(sc.airports, sc.metar)))
    plan["ground_delay_min"] = plan["ground_delay_min"].fillna(0)
    for idx in plan.index:
        g = plan.at[idx, "ground_delay_min"]
        if g:
            plan.at[idx, "facts"] = {**plan.at[idx, "facts"], "ground_delay_min": int(g),
                                     "est_flight_min": int(plan.at[idx, "est_flight_min"]),
                                     "decision_time": pd.Timestamp(plan.at[idx, "decision_time"]).isoformat()}
    plan["in_block"] = plan["landing"] + pd.Timedelta(minutes=C.TAXI_IN_MIN)
    plan["delay_min"] = ((plan["in_block"] - plan["scheduledinblocktime"]).dt.total_seconds() / 60).round()
    plan.loc[plan["action"] != "land", "delay_min"] = C.DIVERTED_DELAY_MIN

    # stands, around already-parked aircraft. Pass 1 keeps every original stand that
    # still works; pass 2 moves only the rest, so moves never cascade.
    horizon = plan["in_block"].max() + pd.Timedelta(hours=24)
    board = StandBoard(sc.stands, sc.parked, horizon)
    plan["new_stand"] = None
    plan["stand_facts"] = None
    order = plan[plan["action"] == "land"].sort_values("in_block").index
    t_out = plan["in_block"] + pd.to_timedelta(plan["turn_min"], unit="m")
    for idx in order:
        s = board.keep_original(plan.loc[idx], plan.at[idx, "in_block"], t_out[idx])
        if s is not None:
            plan.at[idx, "new_stand"] = s
            plan.at[idx, "stand_facts"] = {"kept_original": True}
    for idx in order:
        if plan.at[idx, "new_stand"] is None:
            s, facts = board.assign(plan.loc[idx], plan.at[idx, "in_block"], t_out[idx])
            plan.at[idx, "new_stand"] = s
            plan.at[idx, "stand_facts"] = facts
    return plan
