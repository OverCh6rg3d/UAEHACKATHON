"""Settings and planning assumptions for the DABAB engine.

Every number here that is not measured from the data is an ASSUMPTION and is
written into plans.json so the dashboard and pitch can show it.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "dabab_data_pipeline" / "dabab_data" / "processed"
TZ = "Asia/Dubai"

# ---- Measured from the Dubai Airports data (see engine/README.md) ----
TAXI_IN_MIN = 8            # median taxi-in at DXB, all arrivals May 2025 - Nov 2026
NORMAL_CAPACITY_PER_H = 36  # 95th percentile of hourly DXB landings = practical 2-runway capacity
DIVERTED_DELAY_MIN = 241   # median delay of inferred diverted/held flights on 3 Jan 2026

# ---- Planning assumptions (labelled in output) ----
# Holding fuel burn, kg per minute, by ICAO size class (typical published ranges).
HOLD_BURN_KG_MIN = {"C": 40, "D": 70, "E": 110, "F": 190, "unknown": 60}
CO2_PER_KG_FUEL = 3.16     # ICAO jet fuel emission factor
# Default stand occupancy if the aircraft's real turnaround is unknown (minutes).
TURNAROUND_MIN = {"C": 90, "D": 120, "E": 150, "F": 180, "unknown": 120}
# Remote/bus stand used when no contact stand fits: counted, never a conflict.
REMOTE_STAND = "REMOTE"
# Diversion acceptance per alternate during the event (aircraft). Not in open data.
ALTERNATE_CAPACITY = {"OMDW": 25, "OMAA": 15, "OMSJ": 10, "OMRK": 6, "OMFJ": 6, "OMAL": 6}
# Minutes of flying from the DXB holding area to each alternate (rough, by distance).
CRUISE_KM_PER_MIN = 7.0
DIVERSION_FIXED_MIN = 10   # approach and landing at the alternate

# ---- Ground delay at origin ----
# DABAB acts when fog is forecast. Flights that have not yet taken off at that moment
# are given a landing slot and wait on the ground at origin: no fuel burned, no
# diversion. Airborne flights keep the holding stack.
GROUND_DELAY = True
# Decision this long before fog onset. 120 min = the 1-3 h fog early warning in the
# roadmap. Earlier decisions hold more flights on the ground (biggest single lever).
DECISION_LEAD_MIN = 120
AIRBORNE_BUFFER_MIN = 5    # ground-held flights arrive this long before their slot
GROUND_DELAY_MAX_MIN = 120  # no flight waits longer than this at origin
# Approximate block time to DXB (minutes) by the first letters of the origin ICAO
# code (ICAO region prefixes). Longest prefix wins. Planning values only.
FLIGHT_MIN_BY_PREFIX = {
    "OM": 45, "OO": 60, "OB": 70, "OT": 70, "OK": 110, "OE": 130, "OI": 100, "OR": 150,
    "OJ": 190, "OL": 200, "OS": 200, "OY": 160, "OP": 160, "OA": 170,
    "HE": 220, "HS": 240, "HA": 240, "H": 330,
    "V": 240, "U": 300, "LT": 270, "L": 390, "E": 420, "F": 480, "D": 480, "G": 480,
    "W": 480, "R": 540, "Z": 480, "Y": 780, "N": 840, "K": 840, "C": 840, "S": 900, "T": 900,
}


def est_flight_min(origin_icao) -> int:
    code = str(origin_icao or "")
    for n in (2, 1):
        if code[:n] in FLIGHT_MIN_BY_PREFIX:
            return FLIGHT_MIN_BY_PREFIX[code[:n]]
    return 360


# ---- Optimisation profiles: how the remaining choices are traded off ----
# Safety is NOT a profile: medical and low-fuel flights always go first, and no
# flight holds beyond its fuel limit, in every profile.
# A diversion costs ~4 hours of delay, so fewest diversions also gives the lowest
# average delay; "arrival_order" is kept as the no-re-prioritisation reference.
PROFILES = {
    "min_diversions": {
        "label": "Fewest diversions",
        "goal": "Land flights nearest their fuel limit first so the fewest must divert; also the lowest average delay.",
        "divert_if_hold_over_min": None,
    },
    "protect_connections": {
        "label": "Protect connections",
        "goal": "Land flights carrying the most connecting passengers first.",
        "divert_if_hold_over_min": None,
    },
    "min_fuel": {
        "label": "Minimum fuel and CO2",
        "goal": "Land the heaviest fuel burners first, so the least fuel is burned in the hold.",
        # set a number (minutes) to also divert flights facing a longer projected hold
        "divert_if_hold_over_min": None,
    },
    "arrival_order": {
        "label": "Arrival order (reference)",
        "goal": "First come, first served, no ground delays, same safety floor: shows what coordination adds.",
        "divert_if_hold_over_min": None,
        "ground_delay": False,
    },
}
