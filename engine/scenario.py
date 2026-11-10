"""Load one weather scenario from the data pipeline's processed files."""
import json
from dataclasses import dataclass

import pandas as pd

from . import config as C


@dataclass
class Scenario:
    date: str
    summary: dict
    flights: pd.DataFrame       # one row per arrival to (re)plan
    capacity: dict              # local hour (int) -> landings per hour
    slots: list                 # landing slot times (Timestamps), ascending
    stands: pd.DataFrame        # DXB stands: stand, lat, lon, size_class, apron
    parked: pd.DataFrame        # aircraft not being re-planned that occupy stands
    airports: pd.DataFrame      # UAE airport network
    metar: pd.DataFrame         # all UAE METARs for the day (local time)
    normal_delay_min: float     # mean arrival delay on normal days, same window


def _local(s):
    return pd.to_datetime(s, utc=True, errors="coerce").dt.tz_convert(C.TZ)


def _normal_delay(date: str) -> float:
    """Mean arrival delay in the same clock window on nearby normal days (from script 06)."""
    p = C.PROCESSED / "weather_impact_events.csv"
    if p.exists():
        ev = pd.read_csv(p)
        row = ev[ev["date"] == date]
        if not row.empty:
            return float(row["base_mean_delay_min"].iloc[0])
    return 11.0  # average across all fog events, if 06 has not been run


def _alert(d, summary) -> dict:
    """Fog model output for the day (from 07_fog_model.py): states and lead times."""
    p = d / "alert_timeline.csv"
    if not p.exists():
        return None
    t = pd.read_csv(p)
    t["valid_local"] = pd.to_datetime(t["valid_local"], utc=True).dt.tz_convert(C.TZ)
    onset = pd.Timestamp(summary["fog_start_local"])
    before = t[t["valid_local"] < onset]

    def run_start(states):
        """Start of the unbroken run of these states that leads up to fog onset."""
        ok = before["state"].isin(states).values
        if not len(ok) or not ok[-1]:
            return None
        j = len(ok) - 1
        while j > 0 and ok[j - 1]:
            j -= 1
        return before["valid_local"].iloc[j]

    watch, warn = run_start(["WATCH", "WARNING"]), run_start(["WARNING"])
    lead = lambda x: None if x is None else round((onset - x).total_seconds() / 60)
    mp = C.PROCESSED / "fog_model" / "metrics.json"
    model = json.loads(mp.read_text()) if mp.exists() else {}
    lv = model.get("levels", {})
    return {
        "watch_start": None if watch is None else watch.isoformat(), "watch_lead_min": lead(watch),
        "warning_start": None if warn is None else warn.isoformat(), "warning_lead_min": lead(warn),
        "fog_observed": onset.isoformat(),
        "timeline": [{"time": r.valid_local.isoformat(), "state": r.state,
                      "visibility_m": None if pd.isna(r.vis_m) else int(r.vis_m),
                      "fog_probability_3h": None if pd.isna(r.fog_probability_3h) else round(r.fog_probability_3h, 3)}
                     for r in t.itertuples()],
        "model": {
            "name": model.get("model"), "trained_on": model.get("history"), "test_period": model.get("split", {}).get("test"),
            "watch_test": lv.get("WATCH", {}).get("test"), "warning_test": lv.get("WARNING", {}).get("test"),
            "note": "The replay day is in the test period: the model never saw it in training.",
        },
    }


def build_slots(capacity: dict, start, n_needed: int) -> list:
    """Evenly spaced landing slots inside each hour, from `start` until there are enough."""
    slots, hour = [], start.floor("h")
    while len(slots) < n_needed * 2 + 60:
        cap = capacity.get(hour.hour, C.NORMAL_CAPACITY_PER_H)
        step = pd.Timedelta(minutes=60 / cap)
        t = hour
        while t < hour + pd.Timedelta(hours=1):
            if t >= start:
                slots.append(t)
            t += step
        hour += pd.Timedelta(hours=1)
    return slots


def scaled(sc: "Scenario", factor: float) -> "Scenario":
    """Same scenario with the reduced (weather-hit) landing rates scaled, for sensitivity runs."""
    from dataclasses import replace
    cap = {h: (max(1, round(c * factor)) if c < C.NORMAL_CAPACITY_PER_H else c)
           for h, c in sc.capacity.items()}
    return replace(sc, capacity=cap, slots=build_slots(cap, sc.flights["eta"].min().floor("h"), len(sc.flights)))


def load(date: str) -> Scenario:
    d = C.PROCESSED / f"scenario_{date}"
    if not d.exists():
        raise SystemExit(f"{d} not found. Run 05_build_fog_scenario.py --date {date} first.")
    summary = json.loads((d / "summary.json").read_text())
    summary["alert"] = _alert(d, summary)
    if summary["alert"] and summary["alert"]["watch_lead_min"] is not None:
        # DABAB cannot decide before the model raises a Watch
        summary["decision_lead_min"] = int(min(C.DECISION_LEAD_MIN, summary["alert"]["watch_lead_min"]))

    f = pd.read_csv(d / "arrivals.csv", dtype={"aodbuniquefield": str})
    for c in ["scheduledinblocktime", "actuallandingtime", "actualinblocktime"]:
        f[c] = _local(f[c])
    f = f[f["flightstatus"] != "Cancelled"].dropna(subset=["scheduledinblocktime"]).copy()
    f["size_class"] = f["size_class"].fillna("unknown")
    normal = _normal_delay(date)
    # ETA at the runway if the weather were normal: schedule minus taxi-in, plus the
    # normal lateness of this window (so plans are not credited with origin delays).
    f["eta"] = (f["scheduledinblocktime"] - pd.Timedelta(minutes=C.TAXI_IN_MIN)
                + pd.Timedelta(minutes=normal)).dt.round("min")
    # Fuel limit: latest time the flight can still be landing at DXB.
    f["deadline"] = f["eta"] + pd.to_timedelta(f["syn_fuel_reserve_min"], unit="m")

    occ = pd.read_csv(d / "stand_occupancy.csv", dtype={"aodbuniquefield": str})
    for c in ["actualinblocktime", "off_block"]:
        occ[c] = _local(occ[c])
    # real turnaround of each re-planned flight, used to size its stand block
    occ["turn_min"] = (occ["off_block"] - occ["actualinblocktime"]).dt.total_seconds() / 60
    f = f.merge(occ.loc[occ["in_window"], ["aodbuniquefield", "turn_min"]], on="aodbuniquefield", how="left")
    default_turn = f["size_class"].map(C.TURNAROUND_MIN).fillna(120)
    f["turn_min"] = f["turn_min"].where(f["turn_min"].between(20, 24 * 60), default_turn)
    parked = occ[~occ["in_window"]].copy()

    stands = pd.read_csv(C.PROCESSED / "stands.csv")
    stands = stands[stands["airport"] == "OMDB"][["stand", "lat", "lon", "apron", "size_class"]]

    hourly = pd.read_csv(d / "hourly_landings.csv")
    wx = summary
    t0, t1 = pd.Timestamp(wx["fog_start_local"]), pd.Timestamp(wx["fog_end_local"])
    capacity = {}
    for r in hourly.itertuples():
        in_event = t0.floor("h").hour <= r.hour <= t1.floor("h").hour
        # during the event: what DXB actually achieved (measured); else practical capacity
        capacity[int(r.hour)] = int(r.fog_day) if in_event and r.fog_day > 0 else C.NORMAL_CAPACITY_PER_H
    slots = build_slots(capacity, f["eta"].min().floor("h"), len(f))

    airports = pd.read_csv(C.PROCESSED / "uae_airports.csv")
    met = pd.read_csv(C.PROCESSED / "metar_clean.csv")
    met["valid_local"] = _local(met["valid_utc"])
    day = pd.Timestamp(date).date()
    met = met[met["valid_local"].dt.date == day][["station", "valid_local", "vis_m", "wxcodes"]]

    return Scenario(date, summary, f.reset_index(drop=True), capacity, slots, stands,
                    parked, airports, met, normal)
