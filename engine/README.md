# DABAB engine

Turns a weather scenario (built by `dabab_data_pipeline/.../05_build_fog_scenario.py`)
into ranked recovery plans, and compares them with what actually happened.

```bash
python -m engine.run --date 2026-01-03
```

Output: `dabab_data_pipeline/dabab_data/processed/scenario_<date>/plans.json`

## LLM explanations (optional)

```bash
python -m engine.run --date 2026-01-03 --llm
```

Needs `DABAB/.env` (git-ignored) with:

```
GEMINI_API_KEY=your-key        # free key: aistudio.google.com -> Get API key
GEMINI_MODEL=gemini-2.5-flash  # any Gemini model your key can use
```

- Gemini rewrites each profile's three plan explanations in English and Arabic,
  from the plans' metrics only (`engine/llm.py`, `facts_for`).
- **Grounding check:** every number in the answer must appear in those facts
  (Arabic-Indic digits included). One unknown number and the whole answer is
  rejected; the template text is used instead.
- Accepted answers are cached in `scenario_<date>/explanations_llm.json`, so the live
  demo makes no API call. Delete that file to regenerate.
- No key, a placeholder key, a failed call or a rejected answer never breaks the run:
  templates are always there. `plans.json` says which was used:
  top-level `explanations` and per plan `explanation_source` ("llm" or "template"),
  with the template version kept in `explanation_template`.

## How a plan is built (simplified simulation, label it as such)

1. **Capacity.** Landing slots per hour: the landings DXB actually achieved in each
   fog hour (measured), and 36 per hour otherwise (95th percentile of all hours).
2. **Ground delay at origin.** DABAB decides 120 min before fog onset. Flights not yet
   departed (flight time estimated by origin region) get a slot and wait on the
   ground, max 120 min, burning no fuel.
3. **Sequencing.** At every slot, the waiting flight with the highest priority lands.
   - Safety floor, always: medical flights first, then flights within 15 min of
     their fuel limit. No landing is planned within 5 min of a fuel limit.
   - Then the **priority profile** (chosen by the controller) decides: arrival order
     (min delay), heaviest fuel burner first (min fuel), earliest fuel deadline
     (min diversions) or most connecting passengers (protect connections).
4. **Three recovery plans per profile**, differing in how early they divert:
   - **A Hold all at DXB:** divert only when a flight reaches its fuel limit.
   - **B Balanced:** also divert at once any flight that cannot land before its limit.
   - **C Early diversion:** also divert any flight facing a hold over 45 min.
5. **Diversions.** Alternates are ranked by weather at that time vs ILS minima, A380
   acceptance, flying time, remaining capacity and ground transfer back to DXB.
6. **Stands.** Each landed flight keeps its own stand if it fits and is free, otherwise
   the nearest fitting stand, otherwise remote. Overlaps are impossible.
7. **Recommendation.** Lowest of 0.6 x the profile's measure + 0.4 x risk index, each
   scaled 0-1 across the three plans (`RECOMMEND_WEIGHTS` in config.py).
8. **Risk index.** 100 x (0.5 x flights landing with < 15 min fuel margin + 0.3 x
   flights holding > 30 min + 0.2 x diverted flights) / all flights. Transparent, not
   a certified safety metric.
9. **Confidence.** Share of 9 sensitivity runs (decision lead 60/120/180 min x fog
   landing rate 90/100/110%) in which the same plan stays recommended.

## plans.json format, schema `dabab.plans.v2` (contract with the dashboard)

```jsonc
{
  "schema": "dabab.plans.v2",
  "scenario": {
    "date": "2026-01-03", "airport": "OMDB", "replay": true,
    "weather": {"type": "fog", "start": "ISO", "end": "ISO", "min_visibility_m": 193},
    "decision_time": "ISO",
    "capacity_per_hour": {"7": 15, "8": 19, "9": 36},
    "landings_fog_hours": {"7": 15, "8": 19},          // header: "15 vs 28 normal"
    "landings_normal_same_hours": {"7": 28, "8": 27},
    "flights": 185
  },
  "alert": {                                             // fog model (07_fog_model.py)
    "watch_start": "ISO", "watch_lead_min": 334,         // WATCH: fog likely within hours
    "warning_start": "ISO", "warning_lead_min": 22,      // WARNING: fog imminent
    "fog_observed": "ISO",                               // ALERT: fog in the METAR
    "timeline": [{"time": "ISO", "state": "CLEAR" | "WATCH" | "WARNING" | "ALERT",
                  "visibility_m": 9994, "fog_probability_3h": 0.01}],
    "model": {"name": "...", "watch_test": {}, "warning_test": {}, "note": "..."}
  },
  "safety_floor": [{"en": "...", "ar": "..."}],          // the "always enforced" list
  "airports": [{                                         // airports table and map
    "icao": "OMDW", "iata": "DWC", "name": "...", "lat": 0, "lon": 0,
    "ils_cat": "III", "usable_in_dense_fog": true, "a380": "yes",
    "min_visibility_m_during_event": 306, "weather_ok_during_event": true,
    "km_from_dxb": 41.8, "transfer_min_to_dxb": 41, "diversion_capacity_assumed": 25
  }],
  "explanations": {"status": "llm" | "mixed" | "template" | "off", "fallback_reasons": ["..."]},
  "risk_index": {"formula": "...", "note": "..."},
  "recommendation_rule": "...",
  "assumptions": ["plain-language list, show in the UI"],
  "actual": {"label": "As it happened", "metrics": {"avg_delay_min": 66.5, "diversions": 21},
             "notes": ["..."], "flights": [{"flight": "EK 112", "landing": "ISO", "delay_min": 0}]},
  "reference": {"id": "no_coordination", "label": "No coordination", "metrics": {}},  // point "D" on the chart
  "profiles": [{
    "id": "min_delay" | "min_fuel" | "min_diversions" | "protect_connections",
    "label": "Minimum delay", "label_ar": "...", "objective": "avg_delay_min",
    "recommended": "A",
    "confidence": {"pct": 89, "agree": 8, "runs": 9, "method": "..."},
    "plans": [{
      "id": "A" | "B" | "C", "key": "hold_all" | "balanced" | "early_diversion",
      "label": "Hold all at DXB", "label_ar": "...",
      "recommended": true, "score": 0.4, "dominated": false,
      "metrics": {
        "avg_delay_min": 0.0, "median_delay_min": 0.0,
        "pct_delayed_over_15": 0.0, "pct_delayed_over_60": 0.0,
        "ground_held_flights": 0, "total_ground_delay_min": 0,
        "total_hold_min": 0, "max_hold_min": 0,
        "diversions": 0, "early_diversions": 0, "diversions_by_airport": {"OMDW": 0},
        "fuel_kg": 0, "fuel_t": 0.0, "co2_t": 0.0,
        "connecting_pax_at_risk": 0,
        "low_margin_landings": 0, "long_holds": 0, "min_fuel_margin_min": 5,
        "risk_index": 0.0,
        "stand_conflicts": 0, "stand_changes": 0, "remote_stands": 0
      },
      "explanation": {
        "en": {"why": "...", "cost": "...", "why_not": ["A (...): ...", "C (...): ..."]},
        "ar": {"why": "...", "cost": "...", "why_not": ["..."]}
      },
      "explanation_source": "llm" | "template",
      "explanation_template": {"en": {}, "ar": {}},   // present after a --llm run
      "flights": [{
        "id": "2601056890", "flight": "EK 112", "airline": "EK", "origin": "BUD",
        "aircraft": "B77W", "size_class": "E", "eta": "ISO",
        "action": "land" | "divert",
        "landing": "ISO" | null, "in_block": "ISO" | null,
        "ground_delay_min": 0, "hold_min": 0, "delay_min": 0, "fuel_reserve_min_syn": 60,
        "stand": "B17" | "REMOTE" | null, "original_stand": "B17", "stand_changed": false,
        "divert_to": null | "OMDW", "divert_to_iata": null | "DWC",
        "priority": "medical" | "low_fuel" | "profile",
        "reason": {"code": "...", "facts": {"numbers the explanation may quote": 0}},
        "text": {"en": "one-line reason", "ar": "..."}
      }]
    }]
  }]
}
```

Dashboard mapping: profile chips = `profiles[]`; plan cards = `profiles[i].plans[]`;
"why this plan / what it costs / why not the others" = `explanation`; delay-vs-risk
chart = each plan's `avg_delay_min` and `risk_index`, plus `reference` as the
filtered-out point; confidence = `profiles[i].confidence.pct`.

`reason.facts` holds only numbers produced by the engine or read from the data.
The explanation layer (templates or LLM) may quote these and nothing else. The
Arabic text needs a native-speaker review.
