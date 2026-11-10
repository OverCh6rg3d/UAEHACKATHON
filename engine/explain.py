"""Template explanations in English and Arabic.

Grounded by construction: every number comes from the engine's metrics or a
flight's reason facts. An LLM can later rewrite these, quoting the same facts only.
The Arabic text needs a native-speaker review before the pitch.
"""
from . import config as C

IATA = {"OMDB": "DXB", "OMDW": "DWC", "OMAA": "AUH", "OMSJ": "SHJ", "OMRK": "RKT",
        "OMFJ": "FJR", "OMAL": "AAN"}

# objective -> (English phrase, Arabic phrase, formatter)
METRIC = {
    "avg_delay_min": ("average delay", "متوسط التأخير", lambda v: f"{v:.0f} min", lambda v: f"{v:.0f} دقيقة"),
    "fuel_kg": ("extra fuel", "الوقود الإضافي", lambda v: f"{v / 1000:.0f} t", lambda v: f"{v / 1000:.0f} طن"),
    "diversions": ("diversions", "التحويلات", lambda v: f"{v:.0f}", lambda v: f"{v:.0f}"),
    "connecting_pax_at_risk": ("connecting passengers at risk", "ركاب الربط المعرّضون للخطر",
                               lambda v: f"{v:.0f}", lambda v: f"{v:.0f}"),
}


def _airports(by_ap: dict) -> str:
    return ", ".join(f"{IATA.get(k, k)} {v}" for k, v in by_ap.items()) or "-"


def plan_text(plan: dict, others: list, profile_id: str, recommended: bool, strategies=None) -> dict:
    """why / cost / why_not for one plan, in en and ar."""
    strategies = strategies or C.STRATEGIES
    m, s = plan["metrics"], strategies[plan["id"]]
    obj = C.PROFILES[profile_id]["objective"]
    name, name_ar, fmt, fmt_ar = METRIC[obj]
    early = m["early_diversions"]
    if s["early"] == "none" and not s.get("ground_delay", True):
        why = (f"Every flight holds in the air at DXB; no ground holds at origin. Diverts only when a flight "
               f"reaches its fuel limit ({m['diversions']} diversions).")
        why_ar = (f"تنتظر كل الرحلات في الجو فوق دبي دون انتظار أرضي في مطار المغادرة، ولا تحويل إلا عند بلوغ حدّ الوقود "
                  f"({m['diversions']} تحويلات).")
    elif s["early"] == "none":
        why = (f"Keeps every flight in the DXB queue and diverts only when a flight reaches its fuel limit "
               f"({m['diversions']} diversions). {m['ground_held_flights']} flights wait on the ground at origin.")
        why_ar = (f"تُبقي جميع الرحلات في طابور الهبوط في دبي ولا تحوّل أي رحلة إلا عند بلوغها حدّ الوقود "
                  f"({m['diversions']} تحويلات). تنتظر {m['ground_held_flights']} رحلة على الأرض في مطار المغادرة.")
    elif s["early"] == "unreachable":
        why = (f"Diverts at once the {early} flights that could not land before their fuel limit, so they do not "
               f"burn fuel in the hold first. The rest hold for up to {m['max_hold_min']} min.")
        why_ar = (f"تحوّل فوراً {early} رحلة لا يمكنها الهبوط قبل بلوغ حدّ الوقود، فلا تستهلك وقوداً في الانتظار الجوي. "
                  f"تنتظر بقية الرحلات حتى {m['max_hold_min']} دقيقة.")
    else:
        why = (f"Also diverts flights facing a hold longer than {s['hold_limit_min']} min ({early} early diversions), "
               f"so the queue stays short and {m['low_margin_landings']} flights land with a low fuel margin.")
        why_ar = (f"تحوّل أيضاً الرحلات التي يُتوقع أن تنتظر أكثر من {s['hold_limit_min']} دقيقة ({early} تحويلاً مبكراً)، "
                  f"فيبقى الطابور قصيراً وتهبط {m['low_margin_landings']} رحلة فقط بهامش وقود منخفض.")
    if recommended:
        p = C.PROFILES[profile_id]
        why += f" Recommended for \"{p['label']}\": {name} {fmt(m[obj])}, risk index {m['risk_index']}."
        why_ar += f" موصى بها لأولوية «{p['label_ar']}»: {name_ar} {fmt_ar(m[obj])}، ومؤشر المخاطر {m['risk_index']}."

    cost = (f"{m['diversions']} flights divert ({_airports(m['diversions_by_airport'])}) and need ground transfer or later "
            f"repositioning. Average delay {m['avg_delay_min']:.0f} min, extra fuel {m['fuel_t']:.0f} t "
            f"({m['co2_t']:.0f} t CO2), {m['stand_changes']} stand changes.")
    cost_ar = (f"تُحوَّل {m['diversions']} رحلة ({_airports(m['diversions_by_airport'])}) وتحتاج إلى نقل برّي أو إعادة تموضع لاحقاً. "
               f"متوسط التأخير {m['avg_delay_min']:.0f} دقيقة، والوقود الإضافي {m['fuel_t']:.0f} طن "
               f"({m['co2_t']:.0f} طن CO2)، مع {m['stand_changes']} تغييراً في المواقف.")

    not_en, not_ar = [], []
    for o in others:
        om, os_ = o["metrics"], strategies[o["id"]]
        not_en.append(f"{o['id']} ({os_['label']}): {name} {fmt(om[obj])} vs {fmt(m[obj])}; "
                      f"risk index {om['risk_index']} vs {m['risk_index']}; "
                      f"{om['diversions']} vs {m['diversions']} diversions.")
        not_ar.append(f"{o['id']} ({os_['label_ar']}): {name_ar} {fmt_ar(om[obj])} مقابل {fmt_ar(m[obj])}؛ "
                      f"مؤشر المخاطر {om['risk_index']} مقابل {m['risk_index']}؛ "
                      f"{om['diversions']} مقابل {m['diversions']} تحويلات.")
    return {"en": {"why": why, "cost": cost, "why_not": not_en},
            "ar": {"why": why_ar, "cost": cost_ar, "why_not": not_ar}}


def flight_text(f: dict) -> dict:
    """One-line reason for a single flight's instruction, in en and ar."""
    fx, code = f["reason"]["facts"], f["reason"]["code"]
    if f["action"] != "land":
        to = IATA.get(f["divert_to"], f["divert_to"] or "?")
        cause = {
            "fuel_limit_reached": ("fuel limit reached after holding", "بلغت حدّ الوقود بعد الانتظار"),
            "early_divert_unreachable": (f"projected hold {fx.get('projected_hold_min')} min is too long for its "
                                         f"{fx.get('fuel_reserve_min')} min fuel reserve (5 min safety buffer)",
                                         f"الانتظار المتوقع {fx.get('projected_hold_min')} دقيقة أطول مما يسمح به احتياطي الوقود "
                                         f"({fx.get('fuel_reserve_min')} دقيقة مع هامش أمان 5 دقائق)"),
            "early_divert_long_hold": (f"projected hold {fx.get('projected_hold_min')} min is over the {fx.get('hold_limit_min')} min limit",
                                       f"الانتظار المتوقع {fx.get('projected_hold_min')} دقيقة يتجاوز حدّ {fx.get('hold_limit_min')} دقيقة"),
        }.get(code, ("diverted", "تحويل"))
        rej = "; ".join(f"{IATA.get(k, k)}: {v}" for k, v in fx.get("rejected", {}).items())
        en = (f"Divert to {to} (CAT {fx.get('ils_cat')}, visibility {fx.get('visibility_m')} m, "
              f"{fx.get('fly_min')} min flight): {cause[0]}." + (f" Not used: {rej}." if rej else ""))
        ar = (f"تحويل إلى {to} (CAT {fx.get('ils_cat')}، الرؤية {fx.get('visibility_m')} م، "
              f"{fx.get('fly_min')} دقيقة طيران): {cause[1]}.")
        return {"en": en, "ar": ar}
    pri = {"medical": ("Medical priority: lands first.", "أولوية طبية: تهبط أولاً."),
           "low_fuel": (f"Low fuel: moved ahead, lands with {fx.get('fuel_margin_min')} min margin.",
                        f"وقود منخفض: قُدِّمت في الطابور، تهبط بهامش {fx.get('fuel_margin_min')} دقيقة.")}.get(
        f["priority"], (f"Fuel margin at landing {fx.get('fuel_margin_min')} min.",
                        f"هامش الوقود عند الهبوط {fx.get('fuel_margin_min')} دقيقة."))
    en = f"Hold {f['hold_min']} min, land {f['landing'][11:16]}. {pri[0]}"
    ar = f"انتظار {f['hold_min']} دقيقة، الهبوط {f['landing'][11:16]}. {pri[1]}"
    if f["ground_delay_min"]:
        en = f"Wait {f['ground_delay_min']} min on the ground at origin (no fuel burned). " + en
        ar = f"انتظار {f['ground_delay_min']} دقيقة على الأرض في مطار المغادرة (دون استهلاك وقود). " + ar
    if f["stand_changed"]:
        en += f" Stand {f['stand']} instead of {f['original_stand']}: {fx.get('stand_why', 'original not available')}."
        ar += f" الموقف {f['stand']} بدلاً من {f['original_stand']}."
    else:
        en += f" Stand {f['stand']}."
        ar += f" الموقف {f['stand']}."
    return {"en": en, "ar": ar}
