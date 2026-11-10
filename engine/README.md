# DABAB engine

Turns a weather scenario (built by `dabab_data_pipeline/.../05_build_fog_scenario.py`)
into ranked recovery plans, and compares them with what actually happened.

```bash
python -m engine.run --date 2026-01-03
```

Output: `dabab_data_pipeline/dabab_data/processed/scenario_<date>/plans.json`

## How a plan is built (simplified simulation, label it as such)

1. **Capacity.** Landing slots per hour: the landings DXB actually achieved in each
   fog hour (measured), and 36 per hour otherwise (95th percentile of all hours).
2. **Sequencing.** At every slot, the waiting flight with the highest priority lands.
   - Safety floor, every profile: medical flights first, then flights close to their
     fuel limit. No flight ever holds beyond its fuel limit; if it would, it diverts.
   - Then the profile decides: earliest fuel deadline (fewest diversions, which is
     also the lowest average delay because a diversion costs ~4 hours), most
     connecting passengers (protect connections), heaviest fuel burner first
     (min fuel), or plain arrival order (reference plan).
   - A landing is never planned closer than 5 minutes to a flight's fuel limit.
   - **Ground delay at origin:** DABAB decides 120 min before fog onset (fog early warning). Flights not yet
     departed (flight time estimated by origin region) get a slot and wait on the
     ground, burning no fuel. Airborne flights keep the holding stack. The
     "arrival order" reference plan has no ground delays.
3. **Stands.** Each landed flight gets a stand that fits its aircraft (ICAO size class)
   and is free for its whole turnaround, around aircraft already parked. Its original
   stand is kept when possible, otherwise the nearest fitting stand, otherwise remote.
4. **Diversions.** Alternates are ranked by weather at that time (vs ILS minima),
   A380 acceptance, flying time, remaining capacity and ground transfer back to DXB.

## plans.json format (contract with the dashboard)

```jsonc
{
  "scenario": {
    "date": "2026-01-03", "airport": "OMDB",
    "weather": {"type": "fog", "start": "...", "end": "...", "min_visibility_m": 193},
    "capacity_per_hour": {"5": 36, "7": 15, ...},
    "flights": 185
  },
  "assumptions": ["...plain-language list, show in the UI..."],
  "plans": [
    {
      "id": "actual" | "min_diversions" | "protect_connections" | "min_fuel" | "arrival_order",
      "label": "As it happened" | "Fewest diversions" | ...,
      "goal": "one sentence",
      "is_actual": true | false,
      "metrics": {
        "avg_delay_min": 0.0, "median_delay_min": 0.0,
        "pct_delayed_over_15": 0.0, "pct_delayed_over_60": 0.0,
        "ground_held_flights": 0, "total_ground_delay_min": 0,
        "total_hold_min": 0, "max_hold_min": 0,
        "diversions": 0, "diversions_by_airport": {"OMDW": 0},
        "fuel_kg": 0, "co2_t": 0.0,
        "stand_conflicts": 0, "stand_changes": 0, "remote_stands": 0,
        "connecting_pax_at_risk": 0,
        "min_fuel_margin_min": 0
      },
      "flights": [
        {
          "id": "2601056890", "flight": "EK 112", "origin": "BUD", "aircraft": "B77W",
          "size_class": "E", "eta": "ISO time", "action": "land" | "divert",
          "landing": "ISO time" | null, "in_block": "ISO time" | null,
          "ground_delay_min": 0, "hold_min": 0, "delay_min": 0,
          "stand": "B17" | "REMOTE" | null, "original_stand": "B17", "stand_changed": false,
          "divert_to": null | "OMDW",
          "priority": "medical" | "low_fuel" | "profile",
          "reason": {"code": "...", "facts": {"...": "numbers the explanation may quote"}}
        }
      ]
    }
  ]
}
```

`reason.facts` holds only numbers produced by the engine or read from the data.
The explanation layer (templates or LLM) may quote these and nothing else.
