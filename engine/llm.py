"""LLM explanations (Gemini), grounded on the engine's facts.

The LLM only rewrites the explanation of the three plans of one priority profile
into clearer English and Arabic. It receives the plans' metrics as JSON and must
quote numbers from them only. Every number in its answer is checked against those
facts; one unknown number and the whole answer is rejected, and the template text
is used instead. Answers are cached on disk so the live demo needs no API call.

Setup: put GEMINI_API_KEY (and optionally GEMINI_MODEL) in DABAB/.env.
Key: https://aistudio.google.com -> Get API key.
"""
import hashlib
import json
import os
import re

import requests

from . import config as C

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-2.5-flash"
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
# tokens that contain digits but are names, not quantities
NAME_TOKENS = re.compile(r"CO[2₂]|A380|A388|B77W|CAT\s?I{1,3}|\b[A-Z]{2}\s?\d{2,4}\b|\bRWY\s?\d{2}[LRC]?")

PROMPT = """You explain recovery plans to an air traffic controller at Dubai International during fog.
Rewrite the explanation of the three plans below for the priority profile "{profile}".
Rules:
- Use ONLY numbers that appear in FACTS. Do not compute new numbers (no sums, differences or percentages).
- Write numbers with Western digits (0-9), in both languages.
- Plain, calm, operational language. No marketing words. No safety guarantees.
- Each field at most 45 words.
- "why": why this plan behaves as it does and, if recommended, why it fits the profile.
- "cost": what this plan costs (diversions, delay, fuel, CO2, stand changes).
- "why_not": one short sentence per OTHER plan, comparing it with this plan.
- Arabic: Modern Standard Arabic, same content as English.
Return JSON only, exactly this shape:
{{"plans": {{"A": {{"en": {{"why": "", "cost": "", "why_not": ["", ""]}}, "ar": {{"why": "", "cost": "", "why_not": ["", ""]}}}}, "B": {{...}}, "C": {{...}}}}}}

FACTS:
{facts}
"""


def _env():
    try:
        from dotenv import load_dotenv
        load_dotenv(C.ROOT / ".env")
    except ImportError:
        pass
    key = os.environ.get("GEMINI_API_KEY", "")
    return key, os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)


def available() -> tuple:
    """(usable, reason). A placeholder key counts as not usable."""
    key, _ = _env()
    if not key:
        return False, "GEMINI_API_KEY not set"
    if key.upper().startswith("PLACEHOLDER"):
        return False, "GEMINI_API_KEY is a placeholder"
    return True, "ok"


def facts_for(profile: dict) -> dict:
    """Only what the LLM may quote: profile, recommendation, and each plan's metrics."""
    keep = ["avg_delay_min", "diversions", "early_diversions", "diversions_by_airport", "fuel_t", "co2_t",
            "connecting_pax_at_risk", "risk_index", "low_margin_landings", "max_hold_min",
            "ground_held_flights", "stand_changes"]
    plans = {}
    for p in profile["plans"]:
        m = {k: p["metrics"][k] for k in keep}
        m["diversions_by_airport"] = {C_IATA.get(k, k): v for k, v in m["diversions_by_airport"].items()}
        s = C.STRATEGIES[p["id"]]
        plans[p["id"]] = {"name": p["label"], "name_ar": p["label_ar"], "recommended": p["recommended"],
                          "how_it_diverts": {"none": "diverts only when a flight reaches its fuel limit",
                                             "unreachable": "diverts at once flights that cannot land before their fuel limit",
                                             "long_hold": f"also diverts flights facing a hold over {s.get('hold_limit_min')} min"}[s["early"]],
                          "metrics": m}
    return {"profile": profile["label"], "profile_ar": profile["label_ar"],
            "profile_measure": profile["objective"], "recommended_plan": profile["recommended"],
            "plans": plans}


C_IATA = {"OMDB": "DXB", "OMDW": "DWC", "OMAA": "AUH", "OMSJ": "SHJ", "OMRK": "RKT",
          "OMFJ": "FJR", "OMAL": "AAN"}


def _numbers(obj) -> set:
    """All numbers in the facts, in the forms a writer might use."""
    out = set()
    if isinstance(obj, dict):
        for v in obj.values():
            out |= _numbers(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= _numbers(v)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        for form in {obj, round(obj), round(obj, 1)}:
            out.add(f"{form:g}" if isinstance(form, float) else str(form))
    elif isinstance(obj, str):
        out |= set(re.findall(r"\d+(?:\.\d+)?", obj))
    return out


def ungrounded(text_obj, facts: dict) -> list:
    """Numbers in the LLM output that are not in the facts (empty list = grounded)."""
    allowed = _numbers(facts)
    bad = []
    for s in _strings(text_obj):
        s = NAME_TOKENS.sub(" ", s.translate(ARABIC_DIGITS))
        for n in re.findall(r"\d+(?:[.,]\d+)?", s):
            n = n.replace(",", "")
            if n not in allowed and f"{float(n):g}" not in allowed:
                bad.append(n)
    return bad


def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)


def _valid_shape(out: dict) -> bool:
    try:
        for k in C.STRATEGIES:
            for lang in ("en", "ar"):
                e = out["plans"][k][lang]
                if not (isinstance(e["why"], str) and isinstance(e["cost"], str)
                        and isinstance(e["why_not"], list) and len(e["why_not"]) == len(C.STRATEGIES) - 1):
                    return False
        return True
    except (KeyError, TypeError):
        return False


def call_gemini(prompt: str, timeout: int = 60, retries: int = 3) -> str:
    import time
    key, model = _env()
    for attempt in range(retries + 1):
        r = requests.post(API.format(model=model), timeout=timeout,
                          headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                          json={"contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}})
        if r.status_code in (429, 500, 503) and attempt < retries:
            time.sleep(5 * (attempt + 1))  # busy or rate-limited: wait and retry
            continue
        break
    if r.status_code != 200:
        msg = r.json().get("error", {}).get("message", r.text[:200]) if r.text else r.status_code
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {msg}")
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def explain_profile(profile: dict, cache_path) -> dict:
    """Returns {"status": ..., "plans": {A: {en, ar}, ...} or None, "rejected_numbers": [...]}."""
    facts = facts_for(profile)
    _, model = _env()
    key = hashlib.sha256((model + json.dumps(facts, sort_keys=True)).encode()).hexdigest()[:16]
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    if key in cache:
        return {**cache[key], "cached": True}
    ok, why = available()
    if not ok:
        return {"status": "template", "reason": why, "plans": None}
    try:
        raw = call_gemini(PROMPT.format(profile=profile["label"], facts=json.dumps(facts, ensure_ascii=False, indent=1)))
        out = json.loads(raw)
    except Exception as e:  # network, quota, bad JSON: fall back, never crash the engine
        return {"status": "template", "reason": f"LLM call failed: {e}", "plans": None}
    if not _valid_shape(out):
        return {"status": "template", "reason": "LLM answer had the wrong shape", "plans": None}
    bad = ungrounded(out, facts)
    if bad:  # not cached: the next run tries again
        return {"status": "template", "reason": "LLM used numbers not in the facts",
                "rejected_numbers": sorted(set(bad)), "plans": None}
    res = {"status": "llm", "model": model, "plans": out["plans"]}
    cache[key] = res
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return res
