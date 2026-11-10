"""UAE airport network for the Diversion Balancer, from the GCAA eAIP.

Part 1 - airports table, parsed from each airport's GCAA eAIP AD 2 page:
  AD 2.2  ARP coordinates
  AD 2.12 runway designators and dimensions
  AD 2.14 / AD 2.19  CAT III approach lighting / ILS category -> who can land in fog
Download the pages once (current AIRAC) into raw/gcaa_aip/html/:
  https://www.gcaa.gov.ae/en/ais/AIPHtmlFiles/AIP/Current/AIRACs/2026-P12/html/eAIP/AD-2.OMDB-en-GB.html
  (same pattern for OMDW, OMAA, OMSJ, OMRK, OMFJ, OMAL), saved as AD-2.<ICAO>.html
  The download_pages() helper does this:  python 04_uae_network.py --download

Part 2 - DANS movement statistics (optional calibration) from Dubai Pulse into raw/dans/.

Outputs: processed/uae_airports.csv, processed/dans_monthly_movements.csv
"""
import argparse
import html
import math
import re
import sys

import pandas as pd
import requests

from common import MAIN_AIRPORT, PROCESSED, RAW_DANS, RAW_GCAA_AIP, UAE_AIRPORTS

AIRAC = "2026-P12"   # update every 28 days; cite this in the pitch
EAIP = f"https://www.gcaa.gov.ae/en/ais/AIPHtmlFiles/AIP/Current/AIRACs/{AIRAC}/html/eAIP"
HTML_DIR = RAW_GCAA_AIP / "html"

NAMES = {
    "OMDB": ("DXB", "Dubai International"),
    "OMDW": ("DWC", "Dubai World Central - Al Maktoum International"),
    "OMAA": ("AUH", "Zayed International (Abu Dhabi)"),
    "OMSJ": ("SHJ", "Sharjah International"),
    "OMRK": ("RKT", "Ras Al Khaimah International"),
    "OMFJ": ("FJR", "Fujairah International"),
    "OMAL": ("AAN", "Al Ain International"),
}

# A380 acceptance, read by hand from AD 2 remarks (AIRAC 12/2026). Conservative:
# an airport whose AIP says nothing about A380 operations is treated as "no".
A380_POLICY = {
    "OMDB": ("yes", "A380 stands and push-back rules in AD 2.20"),
    "OMDW": ("yes", "A380 recovery and Emirates SLA in AD 2"),
    "OMAA": ("yes", "Aircraft up to A380 handled, AD 2.4 / 2.20"),
    "OMSJ": ("emirates_only", "AD 2.2 remark: not available for A380 diversions except Emirates"),
    "OMAL": ("yes", "Code F / A380 taxi routing in AD 2.20"),
    "OMRK": ("no", "No A380 provision stated in AIP"),
    "OMFJ": ("no", "No A380 provision stated in AIP"),
}

# Typical ICAO approach minima by ILS category (RVR, metres). Planning values only;
# real minima depend on the procedure and the operator's approval.
MIN_RVR_M = {"III": 75, "II": 300, "I": 550}


def download_pages():
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    for icao in UAE_AIRPORTS:
        r = requests.get(f"{EAIP}/AD-2.{icao}-en-GB.html", timeout=120,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        (HTML_DIR / f"AD-2.{icao}.html").write_bytes(r.content)
        print(f"{icao}: {len(r.content) // 1024} KB")


def dms_to_deg(s: str) -> float:
    """'251510N' or '0552152E' (optionally with decimal seconds) -> decimal degrees."""
    hemi, num = s[-1], s[:-1]
    d_len = 2 if hemi in "NS" else 3
    d, m, sec = int(num[:d_len]), int(num[d_len:d_len + 2]), float(num[d_len + 2:])
    v = d + m / 60 + sec / 3600
    return round(-v if hemi in "SW" else v, 6)


def page_text(icao: str) -> str:
    p = HTML_DIR / f"AD-2.{icao}.html"
    if not p.exists():
        sys.exit(f"Missing {p}. Run: python 04_uae_network.py --download")
    raw = p.read_text(encoding="utf-8", errors="ignore")
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)))


def parse_airport(icao: str) -> dict:
    t = page_text(icao)
    arp = re.search(r"ARP coordinates and site at (?:AD|Aerodrome)\s*"
                    r"(\d{6}(?:\.\d+)?[NS])\s*(\d{7}(?:\.\d+)?[EW])", t)
    i = t.find("AD 2.12")
    rwys = re.findall(r"\b(\d{2}[LRC]?)\s+\d{3}\S*\s*/\s*\d{3}\S*\s+(\d{3,4})\s*x\s*(\d{2,3})",
                      t[i:i + 4000])
    runways = {}
    for des, length, width in rwys:
        runways.setdefault(int(length), (des, int(width)))
    if re.search(r"ILS CAT III|CAT III (?:LIH )?precision approach", t):
        cat = "III"
    elif re.search(r"ILS CAT II\b", t):
        cat = "II"
    else:
        cat = "I"
    iata, name = NAMES[icao]
    a380, a380_note = A380_POLICY[icao]
    longest = max(runways) if runways else None
    return {
        "icao": icao, "iata": iata, "name": name,
        "lat": dms_to_deg(arp.group(1)) if arp else None,
        "lon": dms_to_deg(arp.group(2)) if arp else None,
        "runway_count": len(runways),
        "longest_rwy_m": longest,
        "longest_rwy_width_m": runways[longest][1] if longest else None,
        "runways": "; ".join(f"{d} {l}x{w}" for l, (d, w) in sorted(runways.items(), reverse=True)),
        "ils_cat": cat,
        "approx_min_rvr_m": MIN_RVR_M[cat],
        "a380": a380, "a380_note": a380_note,
        "source": f"GCAA UAE eAIP AD 2.{icao}, AIRAC {AIRAC}",
    }


def km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2 +
         math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(a))


def airports_table() -> pd.DataFrame:
    df = pd.DataFrame([parse_airport(i) for i in UAE_AIRPORTS])
    if df[["lat", "lon"]].isna().any().any():
        sys.exit(f"ARP not parsed for: {df[df.lat.isna()].icao.tolist()}")
    main = df[df.icao == MAIN_AIRPORT].iloc[0]
    df["km_from_main"] = df.apply(lambda r: round(km(main.lat, main.lon, r.lat, r.lon), 1), axis=1)
    # Passenger ground transfer back to DXB: straight line x1.3 road factor at 80 km/h. ESTIMATE.
    df["est_transfer_min"] = (df["km_from_main"] * 1.3 / 80 * 60).round()
    return df


def dans_monthly() -> pd.DataFrame:
    files = sorted(RAW_DANS.glob("*.csv"))
    if not files:
        return pd.DataFrame()
    df = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
    df.columns = [c.strip().lower() for c in df.columns]
    return df.drop_duplicates()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true", help="fetch the eAIP AD 2 pages first")
    if ap.parse_args().download:
        download_pages()
    df = airports_table()
    df.to_csv(PROCESSED / "uae_airports.csv", index=False)
    pd.set_option("display.width", 200)
    print(df[["icao", "iata", "lat", "lon", "longest_rwy_m", "runway_count", "ils_cat",
              "a380", "km_from_main", "est_transfer_min"]].to_string(index=False))
    dm = dans_monthly()
    if not dm.empty:
        dm.to_csv(PROCESSED / "dans_monthly_movements.csv", index=False)
        print(f"\nDANS: {len(dm)} monthly rows")


if __name__ == "__main__":
    main()
