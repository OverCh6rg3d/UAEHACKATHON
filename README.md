# DABAB (ضباب): AI copilot for air traffic control in fog

TDRA Hackathon 2026 · GCAA Challenge Profile #3 · Responsible AI & Smart Cognitive Government · Aviation Safety · AI-Enabled Innovation

DABAB predicts fog, builds three ranked recovery plans for arriving flights (holds, ground delays, diversions, stands), explains each plan in Arabic and English, and lets the controller approve, modify or reject. **The AI predicts, plans and explains. The human decides.**

## Run the demo (one step)

Needs **Python 3.9+** only (no packages).

- **Windows:** double-click `final\run.bat`
- **macOS / Linux:** `sh final/run.sh`
- **Any OS:** `python final/start.py`

The panel opens at **http://localhost:8000**: the 3 Jan 2026 fog replay at Dubai International, on real data. On a fresh clone the script copies the bundled demo data from `final/demo_data/` first. Stop with Ctrl+C.

## Pitch materials (`final/`)

| File | What |
|---|---|
| `DABAB Pitch Deck (Runway lights).pptx` / `.pdf` | The 3-minute pitch deck |
| `hackathonaevideo.mp4` | 10-second hook video |
| `backupdemovideo.mp4` | Screen recording of the dashboard (backup for the live demo) |
| `pitch_slides_text.md` (repo root) | Script, slide text, speaker notes and timings |

## What is in the repo

| Path | What |
|---|---|
| `dabab_atc_panel.html` | ATC decision panel (front end) |
| `server.py` | Backend: serves the panel, `GET /api/scenario`, `POST /api/decision` (audit log + hand-off message) |
| `engine/` | Decision engine: sequencing, ground delay, stands, diversion balancer, plan metrics, stress tests, grounded Gemini explanations ([engine/README.md](engine/README.md)) |
| `dabab_data_pipeline/dabab_data/scripts/` | Data pipeline 01–07: METAR, flights, GCAA stands, UAE airports, fog scenario, weather impact, fog prediction model |
| `final/` | One-step start script, demo data, pitch deck and videos |

## Rebuild everything from raw data (optional)

Needs `pip install -r dabab_data_pipeline/dabab_data/requirements.txt` and the Dubai Airports flight CSVs (Data.Dubai) in `dabab_data_pipeline/dabab_data/raw/dubai_pulse/arrivals|departures/`. From `dabab_data_pipeline/dabab_data/scripts/`:

```bash
python 02_flights_dubai_pulse.py
python 01_weather_metar.py --start 2025-05-01 --end 2026-11-09
python 03_stands_gcaa_aip.py            # needs the GCAA OMDB AD 2-22A/B/C PDFs in raw/gcaa_aip/
python 04_uae_network.py --download
python 06_weather_impact.py
python 07_fog_model.py --download
python 05_build_fog_scenario.py --date 2026-01-03
```

Then from the repo root: `python -m engine.run --date 2026-01-03` (add `--llm` with a `GEMINI_API_KEY` in `.env` for Gemini explanations; templates are used otherwise).

## Data sources

- **Dubai Airports flight information** (arrivals and departures), Data.Dubai / Digital Dubai: 282,705 DXB arrivals, May 2025 – Nov 2026
- **GCAA UAE eAIP**, AIRAC 12/2026: OMDB parking charts (220 stands) and AD 2 pages for 7 UAE airports
- **METAR** reports for 7 UAE airports, Iowa Environmental Mesonet archive, 2014 – 2026

Plan results come from a simplified simulation on real flights, weather and stands; fuel reserves, connecting passengers and medical priority are synthetic. They are indicative.

## Team

Ali Eissa (engine, data, AI, backend) · Mohammed Hishaam (product, ATC panel, pitch)
