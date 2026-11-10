"""Problem evidence: how much do fog, dust and thunderstorms hurt DXB arrivals?

Joins the Dubai Airports arrivals (script 02) with OMDB METARs (script 01).
For every weather event at OMDB it takes the arrivals scheduled during the
event plus a recovery tail, and compares them with the SAME clock hours on
normal days within +/-14 days (controls for time of day and season).

Run after 01 and 02:
    python 06_weather_impact.py

Outputs:
    processed/weather_events.csv          one row per weather event at OMDB
    processed/weather_impact_events.csv   event vs baseline metrics, per event
    processed/weather_impact_summary.csv  averages per weather type
"""
import pandas as pd

from common import MAIN_AIRPORT, PROCESSED

RECOVERY_H = 2          # hours after the last weather report still counted
BASELINE_DAYS = 14      # normal days within +/- this many days form the baseline
DUST = {"DU", "BLDU", "SA", "BLSA", "SS", "DS", "PO"}


def classify(wx: str, is_fog: bool) -> str:
    toks = {t.lstrip("+-") for t in str(wx).split()} if isinstance(wx, str) else set()
    if is_fog:
        return "fog"
    if any(t.startswith("TS") for t in toks):
        return "thunderstorm"
    if toks & DUST:
        return "dust"
    return "normal"


def weather_events(m: pd.DataFrame) -> pd.DataFrame:
    """One event per OMDB date and weather type: first to last report."""
    m = m[m["station"] == MAIN_AIRPORT].copy()
    m["valid_local"] = pd.to_datetime(m["valid_local"], utc=True).dt.tz_convert("Asia/Dubai")
    m["wx_type"] = [classify(w, f) for w, f in zip(m["wxcodes"], m["is_fog"])]
    m["date"] = m["valid_local"].dt.date
    bad = m[m["wx_type"] != "normal"]
    ev = bad.groupby(["date", "wx_type"]).agg(
        start=("valid_local", "min"), end=("valid_local", "max"),
        min_vis_m=("vis_m", "min"), reports=("vis_m", "size")).reset_index()
    # a day with fog counts as fog only (fog dominates the operational impact)
    rank = {"fog": 0, "thunderstorm": 1, "dust": 2}
    ev = ev.sort_values(["date", "wx_type"], key=lambda s: s.map(rank) if s.name == "wx_type" else s)
    ev = ev.drop_duplicates("date", keep="first")
    weather_dates = set(bad["date"])
    return ev.reset_index(drop=True), weather_dates


def metrics(f: pd.DataFrame, landed: int, hours: float) -> dict:
    """f = flights scheduled in the window; landed = landings that happened in it."""
    done = f[f["flightstatus"].isin(["Arrived", "Landed"]) & f["arr_delay_min"].notna()]
    n = len(f)
    return {
        "flights": n,
        "mean_delay_min": done["arr_delay_min"].mean(),
        "median_delay_min": done["arr_delay_min"].median(),
        "pct_late_15": (done["arr_delay_min"] > 15).mean() * 100 if len(done) else float("nan"),
        "pct_diverted": (f["flightstatus"] == "Diverted").mean() * 100 if n else float("nan"),
        "pct_cancelled": (f["flightstatus"] == "Cancelled").mean() * 100 if n else float("nan"),
        "landings_per_hour": landed / hours if hours else float("nan"),
    }


def main():
    a = pd.read_csv(PROCESSED / "flights_arrivals.csv", low_memory=False)
    for c in ["scheduledinblocktime", "actuallandingtime"]:
        a[c] = pd.to_datetime(a[c], utc=True).dt.tz_convert("Asia/Dubai")
    a["date"] = a["scheduledinblocktime"].dt.date
    a["tod"] = (a["scheduledinblocktime"] - a["scheduledinblocktime"].dt.normalize())

    m = pd.read_csv(PROCESSED / "metar_clean.csv")
    ev, weather_dates = weather_events(m)
    ev = ev[(ev["date"] >= a["date"].min()) & (ev["date"] <= a["date"].max())]
    ev.to_csv(PROCESSED / "weather_events.csv", index=False)

    rows = []
    for e in ev.itertuples():
        t0 = e.start - pd.Timedelta(minutes=30)
        t1 = e.end + pd.Timedelta(hours=RECOVERY_H)
        hours = (t1 - t0).total_seconds() / 3600
        def window(x0, x1):
            sched = a[(a["scheduledinblocktime"] >= x0) & (a["scheduledinblocktime"] <= x1)]
            landed = ((a["actuallandingtime"] >= x0) & (a["actuallandingtime"] <= x1)).sum()
            return sched, landed

        hit, hit_landed = window(t0, t1)
        # skip data gaps: flights scheduled but no actual times recorded
        if hit.empty or hit["actuallandingtime"].notna().mean() < 0.5:
            continue
        # baseline: same clock window on normal days within +/- BASELINE_DAYS
        tod0 = t0 - t0.normalize()
        tod1 = t1 - t0.normalize()
        near = [e.date + pd.Timedelta(days=d) for d in range(-BASELINE_DAYS, BASELINE_DAYS + 1) if d]
        near = [d for d in near if d not in weather_dates]
        base_parts, base_landed = [], 0
        for d in near:
            day0 = pd.Timestamp(d, tz="Asia/Dubai")
            s, l = window(day0 + tod0, day0 + tod1)
            if len(s) and s["actuallandingtime"].notna().mean() >= 0.5:
                base_parts.append(s)
                base_landed += l
        if not base_parts:
            continue
        base = pd.concat(base_parts)
        mh = metrics(hit, hit_landed, hours)
        mb = metrics(base, base_landed, hours * len(base_parts))
        row = {"date": e.date, "wx_type": e.wx_type, "min_vis_m": e.min_vis_m,
               "window_start": t0, "window_end": t1, "baseline_days": len(base_parts)}
        row.update({f"event_{k}": v for k, v in mh.items()})
        row.update({f"base_{k}": v for k, v in mb.items()})
        rows.append(row)

    out = pd.DataFrame(rows)
    out.to_csv(PROCESSED / "weather_impact_events.csv", index=False)

    keys = ["mean_delay_min", "median_delay_min", "pct_late_15", "pct_diverted",
            "pct_cancelled", "landings_per_hour"]
    agg = {"events": ("date", "size"), "event_flights": ("event_flights", "sum")}
    for k in keys:
        agg[f"event_{k}"] = (f"event_{k}", "mean")
        agg[f"base_{k}"] = (f"base_{k}", "mean")
    summ = out.groupby("wx_type").agg(**agg).reset_index()
    summ.to_csv(PROCESSED / "weather_impact_summary.csv", index=False)

    pd.set_option("display.width", 200)
    print(f"{len(out)} weather events at {MAIN_AIRPORT} with flight data.\n")
    print(out[["date", "wx_type", "min_vis_m", "event_flights", "event_mean_delay_min",
               "base_mean_delay_min", "event_pct_diverted", "event_landings_per_hour",
               "base_landings_per_hour"]].round(1).to_string(index=False))
    print("\nAverages per weather type (event vs baseline):")
    print(summ.round(1).T.to_string())


if __name__ == "__main__":
    main()
