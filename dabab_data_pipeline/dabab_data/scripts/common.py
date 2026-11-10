"""Shared paths and settings for the DABAB data pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
PROCESSED = ROOT / "processed"

# Where to put files you download by hand (see README.md)
RAW_DUBAI_PULSE_ARRIVALS = RAW / "dubai_pulse" / "arrivals"
RAW_DUBAI_PULSE_DEPARTURES = RAW / "dubai_pulse" / "departures"
RAW_DANS = RAW / "dans"
RAW_GCAA_AIP = RAW / "gcaa_aip"
RAW_METAR = RAW / "metar"

for p in [PROCESSED, RAW_DUBAI_PULSE_ARRIVALS, RAW_DUBAI_PULSE_DEPARTURES,
          RAW_DANS, RAW_GCAA_AIP, RAW_METAR]:
    p.mkdir(parents=True, exist_ok=True)

# UAE airports used in the demo (ICAO codes)
MAIN_AIRPORT = "OMDB"  # Dubai International (DXB)
UAE_AIRPORTS = ["OMDB", "OMDW", "OMAA", "OMSJ", "OMRK", "OMFJ", "OMAL"]

# Time zone of Dubai Pulse timestamps. VERIFY on Day 1: compare a few
# actuallandingtime values with the METAR fog timeline (UTC). If landings
# appear 4 hours off, change this to "UTC".
DUBAI_PULSE_TZ = "Asia/Dubai"

# Visibility below this (metres) counts as fog / low-visibility operations
FOG_VIS_M = 1000
LVP_VIS_M = 550  # roughly where low-visibility procedures bite hard
