"""UAE airport network for the Diversion Balancer, plus optional DANS throughput.

Part 1 - airports table. Fill the TODO columns from each airport's GCAA AIP
page (AD 2.2 for the reference point, AD 2.12 for runways). Coordinates below
are approximate placeholders until you copy the AIP values.

Part 2 - DANS movement statistics (optional calibration). Download the CSVs
from Dubai Pulse into raw/dans/:
  DXB monthly movements: https://www.dubaipulse.gov.ae/data/dans-airport/dans_e_dxb_monthly_movement_stats-open
  DWC monthly movements: https://www.dubaipulse.gov.ae/data/dans-airport/dans_e_dwc_monthly_movement_stats-open

Outputs: processed/uae_airports.csv, processed/dans_monthly_movements.csv
"""
import math

import pandas as pd

from common import MAIN_AIRPORT, PROCESSED, RAW_DANS

AIRPORTS = [
    # icao, iata, name, lat (approx), lon (approx), longest_rwy_m, a380_ok
    ("OMDB", "DXB", "Dubai International", 25.2528, 55.3644, 4447, True),  # rwy from AIP AD 2.12
    ("OMDW", "DWC", "Dubai World Central", 24.8964, 55.1614, None, None),
    ("OMAA", "AUH", "Zayed International (Abu Dhabi)", 24.4330, 54.6511, None, None),
    ("OMSJ", "SHJ", "Sharjah International", 25.3286, 55.5172, None, None),
    ("OMRK", "RKT", "Ras Al Khaimah International", 25.6135, 55.9388, None, None),
    ("OMFJ", "FJR", "Fujairah International", 25.1122, 56.3240, None, None),
    ("OMAL", "AAN", "Al Ain International", 24.2617, 55.6092, None, None),
]


def km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2 +
         math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(a))


def airports_table() -> pd.DataFrame:
    df = pd.DataFrame(AIRPORTS, columns=["icao", "iata", "name", "lat", "lon",
                                         "longest_rwy_m", "a380_ok"])
    main = df[df.icao == MAIN_AIRPORT].iloc[0]
    df["km_from_main"] = df.apply(lambda r: round(km(main.lat, main.lon, r.lat, r.lon), 1), axis=1)
    # Rough road transfer estimate: straight line x1.3, at 80 km/h. Label as estimate.
    df["est_transfer_min"] = (df["km_from_main"] * 1.3 / 80 * 60).round()
    df["coords_source"] = "approximate - replace with GCAA AIP AD 2.2"
    return df


def dans_monthly() -> pd.DataFrame:
    files = sorted(RAW_DANS.glob("*.csv"))
    if not files:
        return pd.DataFrame()
    df = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
    df.columns = [c.strip().lower() for c in df.columns]
    return df.drop_duplicates()


def main():
    ap = airports_table()
    ap.to_csv(PROCESSED / "uae_airports.csv", index=False)
    print(ap[["icao", "name", "km_from_main", "est_transfer_min", "longest_rwy_m"]].to_string(index=False))
    dm = dans_monthly()
    if not dm.empty:
        dm.to_csv(PROCESSED / "dans_monthly_movements.csv", index=False)
        print(f"\nDANS: {len(dm)} monthly rows")


if __name__ == "__main__":
    main()
