# DABAB data pipeline

Four sources, three of them official UAE government data. Each one maps to a moment in the 3-minute demo.

| # | Source | Publisher | What DABAB uses it for | How to get it |
|---|---|---|---|---|
| 1 | Flight arrivals and departures | Dubai Airports, via Dubai Pulse (Digital Dubai) | Real schedules, actual landing and in-block times, aircraft types, **the stand each flight used** | Manual CSV download (below), or API once a key is granted |
| 2 | Aircraft parking/docking charts (stand coordinates, A380-only stands), runways | GCAA, UAE AIP | Official stand map and stand-size rules for the optimizer; runway data for alternates | Manual PDF download, then `03_stands_gcaa_aip.py` |
| 3 | Monthly runway movements (DXB, DWC) | DANS, via Dubai Pulse | Optional: calibrate normal traffic levels | Manual CSV download |
| 4 | METAR weather reports for UAE airports | Issued at UAE aerodromes; free archive at Iowa Environmental Mesonet | Fog timeline: when visibility fell and recovered | Automatic: `01_weather_metar.py` |
| - | Synthetic fields | Our team | Fuel reserve, connecting passengers, medical priority | Generated in `05_build_fog_scenario.py`, all columns start with `syn_` |

## Setup

```
pip install -r requirements.txt
cd scripts
```

## Step 1 - Dubai Pulse flight records (do this first, it decides the replay date)

1. Open both pages and download every CSV file listed:
   - https://www.dubaipulse.gov.ae/data/dubai-airports-flight-info/da_flight_information_arrivals-open
   - https://www.dubaipulse.gov.ae/data/dubai-airports-flight-info/da_flight_information_departures-open
2. Save them into `raw/dubai_pulse/arrivals/` and `raw/dubai_pulse/departures/`.
3. If a page shows **Request Permission**, sign in, accept the terms and submit. Approval can take up to 14 days, so use whatever downloads directly in the meantime.
4. Run `python 02_flights_dubai_pulse.py` and read `processed/flights_coverage.txt`. It tells you which dates you have and how often the stand field is filled.

## Step 2 - METAR weather (automatic)

Download weather for the dates you have flights for, for example a whole winter:

```
python 01_weather_metar.py --start 2023-11-01 --end 2024-03-01
```

`processed/fog_days.csv` ranks the foggiest mornings. Pick one that falls inside your flight data.

## Step 3 - GCAA stand charts

1. Go to the GCAA eAIP (gcaa.gov.ae > AIS > eAIP > current AIRAC) > AD 2 > OMDB.
2. Download the **Aircraft Parking/Docking Charts** (AD 2-22A, 22B, 22C ...) into `raw/gcaa_aip/`.
   Example: https://www.gcaa.gov.ae/en/ais/AIPHtmlFiles/AIP/Current/AIRACs/2026-P08/graphics/OMDB-AD-2-22A_2026-08.pdf
3. Run `python 03_stands_gcaa_aip.py`. Open the output and add stand sizes from the chart symbols into `STAND_OVERRIDES` for the stands you use in the demo.
4. While in the eAIP, copy each alternate airport's longest runway (AD 2.12) and reference point (AD 2.2) into `AIRPORTS` in `04_uae_network.py`.

## Step 4 - Network and DANS (optional CSVs into `raw/dans/`)

```
python 04_uae_network.py
```

## Step 5 - Build the fog-morning scenario

```
python 05_build_fog_scenario.py            # picks the worst fog day you have flights for
python 05_build_fog_scenario.py --date 2024-01-15
```

Outputs go to `processed/scenario_<date>/`: weather timeline, landings per hour (fog day vs normal, i.e. the real capacity drop), arrivals with stand coordinates, stand occupancy, and `summary.json` with the headline numbers.

## Checks on Day 1

- **Time zone:** compare a few landing times with the fog timeline. If they look 4 hours off, change `DUBAI_PULSE_TZ` in `common.py` to `"UTC"`.
- **Departures columns:** the departure field names are detected automatically (`offblock`, `takeoff`). If `dep_delay_min` is missing, check the column names in the CSV.
- **AIRAC dates:** AIP charts are reissued every 28 days. Use the current issue and keep its date in the pitch.
