"""Build the official stand map from the UAE AIP published by the GCAA.

The GCAA's Aeronautical Information Publication (eAIP) includes an
"Aircraft Parking/Docking Chart" for each airport with a table of every stand,
its coordinates and elevation, plus notes on which stands take an A380.

1. Open the GCAA eAIP (https://www.gcaa.gov.ae -> AIS / eAIP -> current AIRAC)
   -> Part 3 AD -> AD 2 -> OMDB -> charts "AD 2-22A", "AD 2-22B", "AD 2-22C"...
   (Aircraft Parking/Docking Charts). Save each PDF into raw/gcaa_aip/.
   Example (AIRAC 08/2026):
   https://www.gcaa.gov.ae/en/ais/AIPHtmlFiles/AIP/Current/AIRACs/2026-P08/graphics/OMDB-AD-2-22A_2026-08.pdf
   Do the same for OMDW (DWC) if you want stands at the main diversion airport.
2. Run:  python 03_stands_gcaa_aip.py
3. Open processed/stands.csv and fill size_class for stands the PDF does not
   label in text (the chart shows them as symbols) using STAND_OVERRIDES below.

Output: processed/stands.csv  (airport, stand, lat, lon, elev_ft, apron, size_class, source)
"""
import re
import sys

import pandas as pd

from common import PROCESSED, RAW_GCAA_AIP, norm_stand

# e.g. "B18L 251454.35N 0552137.22E 12.7"
STAND_RE = re.compile(
    r"\b([A-Z]{1,2}\d{1,3}[LRC]?)\s+"
    r"(\d{2})(\d{2})(\d{2}(?:\.\d+)?)\s*([NS])\s+"
    r"(\d{3})(\d{2})(\d{2}(?:\.\d+)?)\s*([EW])"
    r"(?:\s+(-?\d+(?:\.\d+)?))?"
)

# From the chart notes (OMDB AD 2-22A/B/C, AIRAC 12/2026). Re-check each AIRAC.
A380_ONLY = {"B18R", "B21R", "B26R", "F26R"}
CODE_E_MAX = {"B18L", "B21L", "B26L", "F26L"}
# "for Code F aircraft with solid CL and can be used also for Code D and E"
CODE_F = {"E44", "E45", "C51", "C53", "C54", "C55"}
SIZE_ORDER = ["C", "D", "E", "F"]
# Fill from the chart symbols (Code D/E/F) for the stands you use in the demo.
STAND_OVERRIDES: dict[str, str] = {
    # "A1": "F",
}


def dms(d, m, s, hemi) -> float:
    v = int(d) + int(m) / 60 + float(s) / 3600
    return round(-v if hemi in "SW" else v, 7)


def parse_text(text: str, airport: str, source: str) -> list[dict]:
    rows = []
    for m in STAND_RE.finditer(text):
        sid, la_d, la_m, la_s, la_h, lo_d, lo_m, lo_s, lo_h, elev = m.groups()
        rows.append({
            "airport": airport, "stand": norm_stand(sid),
            "lat": dms(la_d, la_m, la_s, la_h), "lon": dms(lo_d, lo_m, lo_s, lo_h),
            "elev_ft": float(elev) if elev else None,
            "apron": re.match(r"[A-Z]+", sid).group(0), "source": source,
        })
    return rows


def parse_pdf(path) -> list[dict]:
    import pdfplumber
    airport = path.name[:4].upper()
    with pdfplumber.open(path) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    return parse_text(text, airport, f"GCAA UAE AIP {path.name}")


def size_class(stand: str) -> str:
    if stand in STAND_OVERRIDES:
        return STAND_OVERRIDES[stand]
    if stand in A380_ONLY:
        return "F"
    if stand in CODE_E_MAX:
        return "E"
    if stand in CODE_F:
        return "F"
    return "unknown"


def observed_size(stand_ids) -> pd.DataFrame:
    """Largest aircraft class actually parked on each stand (Dubai Airports data).

    The chart shows stand codes only as symbols, so this is the data-driven
    stand capability. A stand that has hosted an A380 can take an A380.
    """
    f = PROCESSED / "flights_arrivals.csv"
    if not f.exists():
        return pd.DataFrame(columns=["stand", "observed_max_class", "observed_flights"])
    a = pd.read_csv(f, usecols=["stand", "size_class"], low_memory=False).dropna()
    a = a[a["stand"].isin(stand_ids) & a["size_class"].isin(SIZE_ORDER)]
    a["rank"] = a["size_class"].map(SIZE_ORDER.index)
    g = a.groupby("stand").agg(rank=("rank", "max"), observed_flights=("rank", "size")).reset_index()
    g["observed_max_class"] = g["rank"].map(lambda r: SIZE_ORDER[r])
    return g[["stand", "observed_max_class", "observed_flights"]]


def main():
    pdfs = sorted(RAW_GCAA_AIP.glob("*.pdf"))
    if not pdfs:
        sys.exit("No PDFs in raw/gcaa_aip/. Download the parking/docking charts first.")
    rows = []
    for p in pdfs:
        got = parse_pdf(p)
        print(f"{p.name}: {len(got)} stands")
        rows += got
    df = pd.DataFrame(rows).drop_duplicates(["airport", "stand"])
    # Sanity check: UAE is roughly 22-27N, 51-57E
    bad = ~df["lat"].between(22, 27) | ~df["lon"].between(51, 57)
    if bad.any():
        print(f"Dropping {bad.sum()} rows with impossible coordinates")
        df = df[~bad]
    df["chart_class"] = df["stand"].map(size_class)
    df = df.merge(observed_size(set(df["stand"])), on="stand", how="left")
    # chart notes win; otherwise the largest aircraft seen there
    df["size_class"] = df["chart_class"].where(df["chart_class"] != "unknown",
                                               df["observed_max_class"]).fillna("unknown")
    df["size_source"] = (df["chart_class"] != "unknown").map({True: "GCAA chart note",
                                                              False: "observed (Dubai Airports)"})
    df.loc[df["size_class"] == "unknown", "size_source"] = "none"
    df = df.sort_values(["airport", "apron", "stand"])
    df.to_csv(PROCESSED / "stands.csv", index=False)
    print(df.groupby(["airport", "apron"]).size().to_string())
    print("\nsize_class:", df["size_class"].value_counts().to_dict())
    print("size_source:", df["size_source"].value_counts().to_dict())


if __name__ == "__main__":
    main()
