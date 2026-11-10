"""Download official METAR reports for UAE airports and find fog mornings.

METARs are the official airport weather reports issued at UAE aerodromes.
The Iowa Environmental Mesonet (IEM) keeps a free public archive of them.

Usage:
    python 01_weather_metar.py --start 2026-01-01 --end 2026-01-06
    python 01_weather_metar.py --start 2023-11-01 --end 2024-03-01   # a whole winter

Outputs:
    raw/metar/metar_<start>_<end>.csv        all reports, all stations
    processed/metar_clean.csv                cleaned, visibility in metres, fog flag
    processed/fog_days.csv                   one row per station per fog day, ranked
"""
import argparse
import io
import time

import pandas as pd
import requests

from common import FOG_VIS_M, PROCESSED, RAW_METAR, UAE_AIRPORTS

IEM_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
FIELDS = ["vsby", "tmpf", "dwpf", "relh", "drct", "sknt", "wxcodes", "metar"]


def download(station: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    params = [("station", station)] + [("data", f) for f in FIELDS] + [
        ("year1", start.year), ("month1", start.month), ("day1", start.day),
        ("year2", end.year), ("month2", end.month), ("day2", end.day),
        ("tz", "Etc/UTC"), ("format", "onlycomma"), ("latlon", "yes"),
        ("missing", "M"), ("trace", "T"), ("direct", "no"),
        ("report_type", "3"), ("report_type", "4"),  # routine + special reports
    ]
    r = requests.get(IEM_URL, params=params, timeout=120)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text), na_values=["M"])


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["valid_utc"] = pd.to_datetime(df["valid"], utc=True)
    df["valid_local"] = df["valid_utc"].dt.tz_convert("Asia/Dubai")
    df["vis_m"] = (pd.to_numeric(df["vsby"], errors="coerce") * 1609.34).round()
    df["temp_c"] = ((pd.to_numeric(df["tmpf"], errors="coerce") - 32) * 5 / 9).round(1)
    df["dew_c"] = ((pd.to_numeric(df["dwpf"], errors="coerce") - 32) * 5 / 9).round(1)
    df["spread_c"] = df["temp_c"] - df["dew_c"]  # small spread = fog risk
    wx = df["wxcodes"].fillna("").astype(str)
    # Fog at the airport = the weather code "FG" (or "FZFG"). Patchy/shallow/
    # vicinity fog (BCFG, MIFG, PRFG, VCFG) is ignored; visibility catches the rest.
    df["fog_code"] = wx.apply(lambda s: any(t in ("FG", "FZFG") for t in s.split()))
    df["is_fog"] = (df["vis_m"] < FOG_VIS_M) | df["fog_code"]
    keep = ["station", "valid_utc", "valid_local", "lat", "lon", "vis_m", "temp_c",
            "dew_c", "spread_c", "relh", "drct", "sknt", "wxcodes", "is_fog", "metar"]
    return df[[c for c in keep if c in df.columns]].sort_values(["station", "valid_utc"])


def fog_days(df: pd.DataFrame) -> pd.DataFrame:
    fog = df[df["is_fog"]].copy()
    if fog.empty:
        return pd.DataFrame()
    fog["date_local"] = fog["valid_local"].dt.date
    out = fog.groupby(["station", "date_local"]).agg(
        fog_start_local=("valid_local", "min"),
        fog_end_local=("valid_local", "max"),
        min_vis_m=("vis_m", "min"),
        fog_reports=("vis_m", "size"),
    ).reset_index()
    out["fog_hours"] = (out["fog_end_local"] - out["fog_start_local"]).dt.total_seconds() / 3600
    return out.sort_values(["min_vis_m", "fog_hours"], ascending=[True, False])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--stations", nargs="*", default=UAE_AIRPORTS)
    a = ap.parse_args()
    start, end = pd.Timestamp(a.start), pd.Timestamp(a.end)

    frames = []
    for st in a.stations:
        print(f"Downloading {st} {a.start} -> {a.end} ...")
        try:
            frames.append(download(st, start, end))
        except Exception as e:  # keep going if one station fails
            print(f"  {st} failed: {e}")
        time.sleep(2)  # be polite to the free archive
    raw = pd.concat(frames, ignore_index=True)
    raw.to_csv(RAW_METAR / f"metar_{a.start}_{a.end}.csv", index=False)

    df = clean(raw)
    df.to_csv(PROCESSED / "metar_clean.csv", index=False)
    fd = fog_days(df)
    fd.to_csv(PROCESSED / "fog_days.csv", index=False)
    print(f"{len(df)} reports; {len(fd)} station-days with fog.")
    print(fd.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
