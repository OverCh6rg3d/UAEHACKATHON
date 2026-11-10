"""Load and clean Dubai Airports flight records from Dubai Pulse (Digital Dubai).

These are the core government datasets for DABAB: real scheduled vs actual
times, aircraft types and the stand each aircraft actually parked at.

Option A (recommended, no key): download the CSV files by hand from
    https://www.dubaipulse.gov.ae/data/dubai-airports-flight-info/da_flight_information_arrivals-open
    https://www.dubaipulse.gov.ae/data/dubai-airports-flight-info/da_flight_information_departures-open
  and save them into raw/dubai_pulse/arrivals/ and raw/dubai_pulse/departures/.

Option B (only once Dubai Pulse emails you an API key and secret): put them in a
  .env file as DUBAI_PULSE_KEY / DUBAI_PULSE_SECRET, copy the dataset's API
  "Query" URL from its page, and run:
    python 02_flights_dubai_pulse.py --api-url "<query url>" --kind arrivals

Then clean everything:
    python 02_flights_dubai_pulse.py

Outputs:
    processed/flights_arrivals.csv, processed/flights_departures.csv
    processed/flights_coverage.txt   <- READ THIS FIRST: which dates you have
"""
import argparse
import os

import pandas as pd
import requests

from common import (DUBAI_PULSE_TZ, PROCESSED, RAW_DUBAI_PULSE_ARRIVALS,
                    RAW_DUBAI_PULSE_DEPARTURES)

TOKEN_URL = ("https://api.dubaipulse.gov.ae/oauth/client_credential/accesstoken"
             "?grant_type=client_credentials")

# Rough ICAO aircraft type -> stand size class (ICAO aerodrome code letter)
SIZE_CLASS = {
    "A388": "F", "B748": "F",
    "B77W": "E", "B773": "E", "B772": "E", "B77L": "E", "B788": "E", "B789": "E",
    "B78X": "E", "A332": "E", "A333": "E", "A339": "E", "A359": "E", "A35K": "E",
    "B744": "E", "B763": "D", "B764": "D", "A306": "D", "A310": "D",
    "A319": "C", "A320": "C", "A321": "C", "A20N": "C", "A21N": "C",
    "B737": "C", "B738": "C", "B739": "C", "B38M": "C", "B39M": "C",
    "E190": "C", "E195": "C", "AT76": "C",
}


# ---------- Option B: API download ----------
def fetch_api(api_url: str, kind: str, page_size: int = 1000) -> pd.DataFrame:
    from dotenv import load_dotenv
    load_dotenv()
    key, secret = os.environ["DUBAI_PULSE_KEY"], os.environ["DUBAI_PULSE_SECRET"]
    tok = requests.post(TOKEN_URL, data={"client_id": key, "client_secret": secret},
                        timeout=60).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}
    rows, offset = [], 0
    while True:
        r = requests.get(api_url, headers=headers, timeout=120,
                         params={"limit": page_size, "offset": offset})
        r.raise_for_status()
        js = r.json()
        batch = js.get("results", js) if isinstance(js, dict) else js
        if not batch:
            break
        rows.extend(batch)
        offset += page_size
        if len(batch) < page_size:
            break
    df = pd.DataFrame(rows)
    out_dir = RAW_DUBAI_PULSE_ARRIVALS if kind == "arrivals" else RAW_DUBAI_PULSE_DEPARTURES
    df.to_csv(out_dir / f"api_{kind}.csv", index=False)
    print(f"Saved {len(df)} {kind} rows from the API.")
    return df


# ---------- Cleaning ----------
def load_folder(folder) -> pd.DataFrame:
    files = sorted(folder.glob("*.csv"))
    if not files:
        return pd.DataFrame()
    df = pd.concat((pd.read_csv(f, low_memory=False) for f in files), ignore_index=True)
    df.columns = [c.strip().lower() for c in df.columns]
    if "aodbuniquefield" in df.columns:  # same flight can appear in several daily files
        sort_col = "lastchanged" if "lastchanged" in df.columns else df.columns[0]
        df = df.sort_values(sort_col).drop_duplicates("aodbuniquefield", keep="last")
    return df


def to_time(df: pd.DataFrame, cols) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            t = pd.to_datetime(df[c], errors="coerce")
            if t.dt.tz is None:
                t = t.dt.tz_localize(DUBAI_PULSE_TZ, ambiguous="NaT", nonexistent="NaT")
            df[c] = t.dt.tz_convert("Asia/Dubai")
    return df


def clean_arrivals(df: pd.DataFrame) -> pd.DataFrame:
    tcols = ["scheduledinblocktime", "estimatedinblocktime", "actuallandingtime",
             "actualinblocktime", "tenmileout", "publicscheduleddatetime", "lastchanged"]
    df = to_time(df, tcols)
    if "traffictypecode" in df.columns:  # keep passenger flights
        df = df[df["traffictypecode"].astype(str).str.upper().str.startswith("P") | df["traffictypecode"].isna()]
    df["size_class"] = df.get("aircraft_icao", pd.Series(index=df.index)).map(SIZE_CLASS).fillna("unknown")
    df["arr_delay_min"] = (df["actualinblocktime"] - df["scheduledinblocktime"]).dt.total_seconds() / 60
    df["taxi_in_min"] = (df["actualinblocktime"] - df["actuallandingtime"]).dt.total_seconds() / 60
    df["stand"] = df.get("aircraftparkingposition", pd.Series(index=df.index)).astype(str).str.strip().replace("nan", pd.NA)
    df["service_date"] = df["scheduledinblocktime"].dt.date
    keep = ["aodbuniquefield", "flightnumber", "airlinecode_iata", "airlinename", "origin_iata",
            "origin_icao", "aircraft_icao", "aircraft_iata", "size_class", "aircraftregistration",
            "aircraftterminal", "stand", "flightstatus", "service_date", "scheduledinblocktime",
            "estimatedinblocktime", "tenmileout", "actuallandingtime", "actualinblocktime",
            "arr_delay_min", "taxi_in_min"]
    return df[[c for c in keep if c in df.columns]]


def clean_departures(df: pd.DataFrame) -> pd.DataFrame:
    # Departure column names are not documented here; detect them by pattern.
    tcols = [c for c in df.columns if any(k in c for k in ("time", "offblock", "takeoff"))]
    df = to_time(df, tcols)
    sched = next((c for c in df.columns if "scheduled" in c and "offblock" in c), None)
    actual = next((c for c in df.columns if "actual" in c and "offblock" in c), None)
    if sched and actual:
        df["dep_delay_min"] = (df[actual] - df[sched]).dt.total_seconds() / 60
        df["service_date"] = df[sched].dt.date
    if "aircraftparkingposition" in df.columns:
        df["stand"] = df["aircraftparkingposition"].astype(str).str.strip().replace("nan", pd.NA)
    if "aircraft_icao" in df.columns:
        df["size_class"] = df["aircraft_icao"].map(SIZE_CLASS).fillna("unknown")
    return df


def coverage_report(arr: pd.DataFrame, dep: pd.DataFrame) -> str:
    lines = []
    for name, d, col in [("Arrivals", arr, "scheduledinblocktime"), ("Departures", dep, None)]:
        if d.empty:
            lines.append(f"{name}: NO FILES FOUND")
            continue
        col = col or next((c for c in d.columns if "scheduled" in c and "offblock" in c), None)
        if col:
            lines.append(f"{name}: {len(d)} flights, {d[col].min()} -> {d[col].max()}")
        if "stand" in d.columns:
            lines.append(f"  stand filled: {d['stand'].notna().mean():.0%}")
        if "service_date" in d.columns:
            per_day = d.groupby("service_date").size()
            lines.append(f"  days: {len(per_day)}, median flights/day: {int(per_day.median())}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-url")
    ap.add_argument("--kind", choices=["arrivals", "departures"], default="arrivals")
    a = ap.parse_args()
    if a.api_url:
        fetch_api(a.api_url, a.kind)

    arr = load_folder(RAW_DUBAI_PULSE_ARRIVALS)
    dep = load_folder(RAW_DUBAI_PULSE_DEPARTURES)
    if not arr.empty:
        arr = clean_arrivals(arr)
        arr.to_csv(PROCESSED / "flights_arrivals.csv", index=False)
    if not dep.empty:
        dep = clean_departures(dep)
        dep.to_csv(PROCESSED / "flights_departures.csv", index=False)
    rep = coverage_report(arr, dep)
    (PROCESSED / "flights_coverage.txt").write_text(rep)
    print(rep)


if __name__ == "__main__":
    main()
