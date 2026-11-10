"""Combine all sources into one fog-morning scenario for the replay and optimizer.

Run after 01-04:
    python 05_build_fog_scenario.py                 # auto-picks the worst fog day you have flights for
    python 05_build_fog_scenario.py --date 2026-01-03

Outputs in processed/scenario_<date>/:
    weather_timeline.csv     OMDB visibility through the morning (NCM/airport METARs)
    hourly_landings.csv      landings per hour on the fog day vs normal days -> real capacity drop
    arrivals.csv             flights in the fog window + stand coordinates + synthetic fields
    stand_occupancy.csv      which stand was busy when (arrival in-block -> departure off-block)
    summary.json             headline numbers for the dashboard and pitch
"""
import argparse
import json

import numpy as np
import pandas as pd

from common import MAIN_AIRPORT, PROCESSED

SEED = 42  # fixed so the demo gives the same numbers every run


def read(name, **kw):
    p = PROCESSED / name
    return pd.read_csv(p, **kw) if p.exists() else pd.DataFrame()


def to_local(s):
    return pd.to_datetime(s, utc=True, errors="coerce").dt.tz_convert("Asia/Dubai")


def pick_date(fog: pd.DataFrame, arr: pd.DataFrame, wanted):
    if wanted:
        return pd.Timestamp(wanted).date()
    days = set(pd.to_datetime(arr["service_date"]).dt.date)
    f = fog[(fog["station"] == MAIN_AIRPORT)].copy()
    f["date_local"] = pd.to_datetime(f["date_local"]).dt.date
    f = f[f["date_local"].isin(days)]
    if f.empty:
        raise SystemExit("No OMDB fog day overlaps your flight data. Download METAR for "
                         "the dates in processed/flights_coverage.txt, or pass --date.")
    return f.sort_values(["min_vis_m", "fog_hours"], ascending=[True, False]).iloc[0]["date_local"]


def enrich_synthetic(df: pd.DataFrame) -> pd.DataFrame:
    """Fields no open dataset has. Clearly labelled synthetic, seeded for repeatability."""
    rng = np.random.default_rng(SEED)
    n = len(df)
    seats = df["size_class"].map({"F": 500, "E": 330, "D": 230, "C": 170}).fillna(180)
    df["syn_fuel_reserve_min"] = rng.integers(20, 61, n)
    df["syn_connecting_pax"] = (seats * rng.uniform(0.2, 0.6, n)).round().astype(int)
    df["syn_medical_priority"] = rng.random(n) < 0.01
    df["is_synthetic_fields"] = "syn_* columns are synthetic"
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--before-h", type=float, default=2)
    ap.add_argument("--after-h", type=float, default=3)
    a = ap.parse_args()

    met, fog = read("metar_clean.csv"), read("fog_days.csv")
    arr, dep = read("flights_arrivals.csv"), read("flights_departures.csv")
    stands = read("stands.csv")
    if arr.empty or met.empty:
        raise SystemExit("Run 01_weather_metar.py and 02_flights_dubai_pulse.py first.")

    day = pick_date(fog, arr, a.date)
    out = PROCESSED / f"scenario_{day}"
    out.mkdir(exist_ok=True)

    # Weather timeline for the day
    met["valid_local"] = to_local(met["valid_utc"])
    wx = met[(met["station"] == MAIN_AIRPORT) & (met["valid_local"].dt.date == day)]
    wx.to_csv(out / "weather_timeline.csv", index=False)
    fog_rows = wx[wx["is_fog"]]
    if fog_rows.empty:
        raise SystemExit(f"No fog reports at {MAIN_AIRPORT} on {day}.")
    t0 = fog_rows["valid_local"].min() - pd.Timedelta(hours=a.before_h)
    t1 = fog_rows["valid_local"].max() + pd.Timedelta(hours=a.after_h)

    # Landings per hour: fog day vs the median of all other days -> data-driven capacity drop
    for c in ["scheduledinblocktime", "actuallandingtime", "actualinblocktime"]:
        arr[c] = to_local(arr[c])
    landed = arr.dropna(subset=["actuallandingtime"]).copy()
    landed["date"] = landed["actuallandingtime"].dt.date
    landed["hour"] = landed["actuallandingtime"].dt.hour
    per = landed.groupby(["date", "hour"]).size().rename("landings").reset_index()
    normal = per[per["date"] != day].groupby("hour")["landings"].median().rename("normal_median")
    fogday = per[per["date"] == day].set_index("hour")["landings"].rename("fog_day")
    hourly = pd.concat([normal, fogday], axis=1).fillna(0).astype(int).reset_index()
    hourly.to_csv(out / "hourly_landings.csv", index=False)

    # Arrivals scheduled in the fog window
    win = arr[(arr["scheduledinblocktime"] >= t0) & (arr["scheduledinblocktime"] <= t1)].copy()
    if not stands.empty:
        s = stands[stands["airport"] == MAIN_AIRPORT][["stand", "lat", "lon", "size_class"]]
        win = win.merge(s.rename(columns={"size_class": "stand_size_class"}), on="stand", how="left")
    win = enrich_synthetic(win)
    win.to_csv(out / "arrivals.csv", index=False)

    # Stand occupancy: arrival in-block until the same aircraft's next off-block
    occ = pd.DataFrame()
    off_col = next((c for c in dep.columns if "actual" in c and "offblock" in c), None) if not dep.empty else None
    if off_col and "aircraftregistration" in dep.columns:
        d = dep.dropna(subset=[off_col, "aircraftregistration"]).copy()
        d["off_block"] = to_local(d[off_col])
        a2 = win.dropna(subset=["actualinblocktime", "aircraftregistration"]).sort_values("actualinblocktime")
        d = d.sort_values("off_block")
        occ = pd.merge_asof(a2, d[["aircraftregistration", "off_block"]],
                            left_on="actualinblocktime", right_on="off_block",
                            by="aircraftregistration", direction="forward",
                            tolerance=pd.Timedelta(hours=24))
        occ = occ[["flightnumber", "aircraftregistration", "stand", "actualinblocktime", "off_block"]]
        occ.to_csv(out / "stand_occupancy.csv", index=False)

    summary = {
        "date": str(day),
        "fog_start_local": str(fog_rows["valid_local"].min()),
        "fog_end_local": str(fog_rows["valid_local"].max()),
        "min_visibility_m": float(fog_rows["vis_m"].min()),
        "arrivals_in_window": int(len(win)),
        "avg_arrival_delay_min": round(float(win["arr_delay_min"].mean()), 1) if len(win) else None,
        "flights_delayed_over_30_min": int((win["arr_delay_min"] > 30).sum()),
        "flights_without_landing_time": int(win["actuallandingtime"].isna().sum()),  # diversions/cancellations proxy
        "stands_with_coordinates": int(win["lat"].notna().sum()) if "lat" in win else 0,
        "peak_hour_normal_landings": int(hourly["normal_median"].max()),
        "min_hour_fog_landings": int(hourly.loc[hourly["normal_median"] > 0, "fog_day"].min()),
        "sources": ["Dubai Airports flight records via Dubai Pulse (Digital Dubai)",
                    "GCAA UAE AIP aircraft parking/docking charts",
                    "METAR reports for UAE airports (IEM archive)",
                    "Synthetic: fuel reserve, connecting passengers, medical priority"],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
