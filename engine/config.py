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


# ---- Priority profiles (chosen by the controller) ----
# A profile sets (1) who lands first when flights compete for a slot and
# (2) which measure decides the recommended plan.
# Safety is NOT a profile: medical and low-fuel flights always go first, and no
# flight holds beyond its fuel limit, in every profile and every plan.
PROFILES = {
    "min_delay": {"label": "Minimum delay", "label_ar": "أقل تأخير",
                  "sequence": "arrival", "objective": "avg_delay_min"},
    "min_fuel": {"label": "Minimum fuel / CO2", "label_ar": "أقل وقود / CO2",
                 "sequence": "burn", "objective": "fuel_kg"},
    "min_diversions": {"label": "Minimum diversions", "label_ar": "أقل تحويلات",
                       "sequence": "deadline", "objective": "diversions"},
    "protect_connections": {"label": "Protect connections", "label_ar": "حماية رحلات الربط",
                            "sequence": "connections", "objective": "connecting_pax_at_risk"},
}

# ---- Recovery plans (three per profile): how early to divert ----
#   none        divert only when a flight reaches its fuel limit
#   unreachable also divert at once any flight that cannot land before its fuel limit
#   long_hold   also divert any flight facing a hold longer than hold_limit_min
STRATEGIES = {
    "A": {"key": "hold_all", "label": "Hold all at DXB", "label_ar": "انتظار الجميع في دبي",
          "early": "none"},
    "B": {"key": "balanced", "label": "Balanced", "label_ar": "متوازنة",
          "early": "unreachable"},
    "C": {"key": "early_diversion", "label": "Early diversion", "label_ar": "تحويل مبكر",
          "early": "long_hold", "hold_limit_min": 45},
}

# ---- Risk index (0-100, lower is better). A transparent formula, not a certified
# safety metric: weighted share of flights in each condition.
RISK_LOW_MARGIN_MIN = 15   # landing with less fuel margin than this
RISK_LONG_HOLD_MIN = 30    # holding longer than this
RISK_WEIGHTS = {"low_margin": 0.5, "long_hold": 0.3, "diverted": 0.2}

# ---- Recommendation: the profile's own measure, tempered by risk ----
# Each is scaled 0-1 across the three plans (0 = best). Lowest score is recommended.
RECOMMEND_WEIGHTS = {"objective": 0.6, "risk": 0.4}

# ---- Confidence: share of sensitivity runs in which the same plan stays best ----
SENSITIVITY_LEADS_MIN = [60, 120, 180]   # decision lead before fog onset
SENSITIVITY_CAPACITY = [0.85, 1.0, 1.15]           # fog landing rate scaled by this
SENSITIVITY_FUEL_SEEDS = [None, 7, 11]             # None = the scenario's own synthetic reserves;
                                                   # others redraw them (30-90 min) with that seed


# ---- Card names: what is actually different about each plan, per profile ----
# (the landing order comes from the profile, the diversion rule from the plan)
CARD_NAMES = {
    "min_delay": {"A": ("Land in arrival order", "الهبوط حسب ترتيب الوصول"),
                  "B": ("Divert fuel-short flights", "تحويل الرحلات قليلة الوقود"),
                  "C": ("Divert long holds", "تحويل الانتظارات الطويلة")},
    "min_fuel": {"A": ("Heavy jets land first", "الطائرات الثقيلة أولاً"),
                 "B": ("Heavy first, divert fuel-short", "الثقيلة أولاً وتحويل قليلة الوقود"),
                 "C": ("Heavy first, early diversion", "الثقيلة أولاً وتحويل مبكر")},
    "min_diversions": {"A": ("Lowest fuel lands first", "الأقل وقوداً تهبط أولاً"),
                       "B": ("Fuel order, divert fuel-short", "حسب الوقود وتحويل قليلة الوقود"),
                       "C": ("Fuel order, early diversion", "حسب الوقود وتحويل مبكر")},
    "protect_connections": {"A": ("Connections land first", "رحلات الربط أولاً"),
                            "B": ("Connections first, divert fuel-short", "الربط أولاً وتحويل قليلة الوقود"),
                            "C": ("Connections first, early diversion", "الربط أولاً وتحويل مبكر")},
}

# ---- Second plan set, offered when the controller rejects all three ----
ALT_STRATEGIES = {
    "A": {"key": "air_hold_only", "label": "No ground holds", "label_ar": "دون انتظار أرضي",
          "early": "none", "ground_delay": False},
    "B": {"key": "divert_over_30", "label": "Divert holds over 30 min", "label_ar": "تحويل الانتظار فوق 30 دقيقة",
          "early": "long_hold", "hold_limit_min": 30},
    "C": {"key": "divert_over_75", "label": "Divert holds over 75 min", "label_ar": "تحويل الانتظار فوق 75 دقيقة",
          "early": "long_hold", "hold_limit_min": 75},
}

# ---- Per-plan reliability: share of stress tests in which the plan's own key result
# stays close to what the card shows (delay 5%, fuel and connections 10%, diversions 2 flights)
RELIABILITY_TOLERANCE = {"avg_delay_min": 0.05, "fuel_kg": 0.10, "connecting_pax_at_risk": 0.10,
                         "diversions_abs": 2}
