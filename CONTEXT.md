# DABAB: project context handoff (updated 10 Nov 2026)

Paste this file into a new chat. It supersedes the earlier DABAB_CONTEXT.md.

## 1. Hackathon
- TDRA UAE Hackathon 2026. Theme: Responsible AI & Smart Cognitive Government. Challenge #2 (GCAA): help air navigation providers, airports and controllers make fast, reliable decisions on aircraft movement and landing-stand allocation during unforeseen weather (fog, emergency weather), using AI, real-time data and integration between air navigation and airport systems.
- Format: submit a proposal, then a 3-minute pitch.
- Grading (Pioneers, six criteria): alignment with challenge and impact 20%; effective use of government open data 15%; innovative use of AI 15%; feasibility and planning (clear 90-day execution plan with milestones) 15%; market potential and commercialization 15%; presentation, clarity and creativity of the pitch 20%.
- Team: 2 people (not 3-4). Proposed split: Person A = engine and evidence (data, optimizer, replay); Person B = product and pitch (Streamlit dashboard, slides, script, demo video). Roles and deadline NOT yet confirmed.

## 2. The idea: DABAB (ضباب, "fog")
Explainable AI copilot shared by air traffic control, airport and airlines. In severe weather it proposes ranked recovery plans, explains each in Arabic and English, and a human always approves. "The AI recommends, explains and is accountable; the human decides."

Core modules: (1) mitigation playbook (OR-Tools optimizer with greedy fallback, 2-3 plans with delay, diversions, stand conflicts, fuel, CO2); (2) explainable cards (reason AR/EN, confidence, why-not-alternatives, Approve/Modify/Reject, audit log; LLM only explains optimizer facts, template fallback); (3) UAE diversion balancer (DXB, DWC, AUH, SHJ, RKT, FJR, AAN as one network); (4) replay of real weather days, actual vs DABAB (simplified simulation, labelled).

### Decisions from the latest discussion (agreed in principle, NOT yet applied to the proposals)
- Scope widened from fog to low-visibility and severe weather: fog is the flagship demo; thunderstorms and dust/sand are the same engine with a different capacity input. Thunderstorms mostly close approach paths rather than cut visibility.
- Modular execution: approved decisions can be sent as structured instructions to downstream systems (airport, airline, ATC, future automated systems) only after human confirmation. We will NOT build an AI landing pilot; say "future automated systems", never promise one.
- Evidence: show less delay and less risk. Delay and safety are not simply positively correlated (long holding burns fuel and cuts margins), so show a delay-vs-risk trade-off curve where each plan is a point and dominated plans are filtered out.
- Option profiles chosen by the controller or operations centre, not the pilot: minimum delay, minimum fuel/CO2, minimum diversions, protect connections. Safety is a fixed floor the optimizer always enforces, not a preference.
- Integration between air navigation and airport systems (named in the challenge): position DABAB as an AI layer on A-CDM; airport side = AODB (Dubai Airports flights/stands), air navigation side = METAR plus GCAA data, with SWIM/FIXM as the named standard interfaces. Pitch line: "One shared picture for air navigation, the airport and airlines."

## 3. Evidence computed so far (real data, script 06)
Dubai Airports arrivals joined with OMDB METAR; each event window = first to last weather report plus 2 h recovery; baseline = same clock hours on normal days within +/-14 days.

| Weather at DXB | Events | Flights | Mean delay min (event vs normal) | >15 min late | Landings/h |
|---|---|---|---|---|---|
| Fog | 5 | 503 | 86 vs 11 | 83% vs 28% | 19.4 vs 22.9 |
| Thunderstorm | 2 | 594 | 102 vs 15 | 81% vs 33% | 22.8 vs 29.1 |
| Dust/sand | 42 | 6,759 | 10 vs 8 | 27% vs 23% | 21.9 vs 21.7 |

- 3 Jan 2026: landings fell to 15/h at 07:00 vs 28 on normal days, matching the METAR fog window. This also confirms the flight data's time zone (Asia/Dubai).
- Small samples (5 fog, 2 thunderstorm events): report as observed averages, not statistical proof.
- Diversions are undercounted in the flight data (3 Jan shows 0; news reported 21 DXB + 2 DWC diverted) because diverted flights that later reach DXB are recorded as Arrived. Use news figures (Gulf News, Khaleej Times) for diversions.
- Fog days at DXB in range: 2026-01-03 (193 m, 07:04-08:30), 2026-02-10 (257 m), 2026-02-23 (306 m), 2025-11-20 (402 m), 2026-02-24 (402 m). Replay story day: 3 Jan 2026; backup 10 Feb. DWC also had fog on 3 Jan. DXB fog events were short (about 1-2 h), so expect a modest replay gain; report honestly as a range.
- Thunderstorm days: 2025-12-18, 2025-12-19.

## 4. Data
- Dubai Airports flight information, arrivals and departures CSVs (Data.Dubai, Digital Dubai; formerly Dubai Pulse). Downloaded by the user, about 120 MB each, in `dabab_data_pipeline/dabab_data/` and copied to `raw/dubai_pulse/arrivals|departures/`. Arrivals: 282,705 flights, 1 May 2025 to 9 Nov 2026, 531 days, median 599/day, stand filled 100%. Departures: 285,022 flights, no origin column so DXB and DWC cannot be separated except by terminal. Dates are intact in these files (earlier samples had lost them via Excel; never open raw files in Excel). The AODB pads text fields with spaces; script 02 now strips them.
- METAR for 7 UAE airports from Iowa Environmental Mesonet (143,830 reports downloaded).
- GCAA AIP OMDB parking charts: only AD 2-22A known (aprons A, B, D, F, S; URL `https://www.gcaa.gov.ae/en/ais/AIPHtmlFiles/AIP/Current/AIRACs/2026-P08/graphics/OMDB-AD-2-22A_2026-08.pdf`). NOT downloaded. Other stands (e.g. Q06, C-apron) need the other charts (22B, 22C...).
- Synthetic (labelled, `syn_` prefix, seed 42): fuel reserve, connecting passengers, medical priority.
- API access to Dubai Pulse/Data.Dubai requested (up to 14 days). Do not claim live integration unless tested.
- Optional/backup: DANS monthly stats, NCM WIS2 SYNOP (3-hourly, too coarse for fog), Bayanat search for a fourth government publisher (not done).

## 5. Code state (repo)
- GitHub: https://github.com/OverCh6rg3d/UAEHACKATHON (branch main). Local: `C:\Users\aliei\My Projects\DABAB`, pipeline in `dabab_data_pipeline/dabab_data/` with `scripts/` 01-06 and `common.py`.
- Commits pushed: e33af49 (initial pipeline), 043c4d9 (script 06 weather impact + whitespace-strip fix in 02).
- `.gitignore` excludes `.env`, `*.csv`, `*.pdf`, `*.zip`, `raw/`, `processed/`, Python/editor clutter. The raw CSVs are NOT in git (about 120 MB each, over GitHub's 100 MB file limit; gzipped about 22 MB each). The user asked to add them to git, then interrupted the attempt before anything was committed; UNRESOLVED. Options: gzip and commit (script 02 would need to read .csv.gz), Git LFS (git-lfs 3.5.1 installed), or each teammate downloads from data.dubai. Until decided, the teammate needs their own CSVs in `raw/dubai_pulse/`.
- Scripts: 01 METAR download + fog days (run on real data, works); 02 flights clean (run, works); 03 stands from GCAA PDFs (not run, needs PDFs); 04 UAE airports table (not run; coordinates are placeholders); 05 build fog scenario (not run, needs 03); 06 weather impact (run, works). Run from `scripts/`: `python 02_flights_dubai_pulse.py`, `python 01_weather_metar.py --start 2025-05-01 --end 2026-11-09`, `python 06_weather_impact.py`.
- Expected checks: coverage.txt shows 282,705 arrivals; fog_days.csv has 5 OMDB days; script 06 prints fog delay about 86 vs 11 min. The user ran script 06 and got matching numbers.
- Not built yet: stand map, optimizer, diversion balancer, replay simulator, dashboard, explanation layer. `DUBAI_PULSE_TZ="Asia/Dubai"` is confirmed correct.
- Script 06 flags thunderstorm (TS codes) and dust (DU, BLDU, SA, BLSA, SS, DS, PO) separately from fog.

## 6. Deliverables (Claude Docs)
- Full proposal: https://claude.ai/artifact/EsEUxQnFUWKGX1EvcqgERR ("DABAB: AI Fog Disruption Copilot"). Updated: data sources table, "The solution", "Evidence from the data", 90-day plan, market and commercialization. Other sections (48-hour build plan, risks...) untouched and predate the new decisions in section 2.
- Short proposal (about 2 pages): https://claude.ai/artifact/95XcqZmjVuh8zFBo8WTMtG ("DABAB: Short Proposal"), includes the evidence section.
- 90-day plan (in both): days 1-30 data and baseline (API access, validate on historical weather days, agree priority rules; milestone: replay accepted by experts); days 31-60 shadow mode (milestone: controllers rate recommendations useful); days 61-90 controlled single-airport pilot (milestone: go/no-go). Business model: customers GCAA and ANSPs, then airports and airlines; per-airport licence/SaaS fee plus integration and training; scalable to other Gulf airports.

## 7. Pitch plan (180 s)
Hook 15 s (3 Jan 2026 fog story; optional video of a controller using the dashboard); challenge 15; evidence 20 (real data chart); prototype and user journey 30 (alert, 3 plans, AR card, Approve, audit log); possibility 10; solution 15; technology 20 (4-box diagram: data, optimizer, grounded explanation, human); business model 15; team 10; pathway 15 (verbs and numbers); closing 15. Reminders: make the challenge clear, evidence visible, technology understandable, impact measurable, pathway believable. The team slide needs the two members' real skills; do not invent them.

## 8. Next steps
1. Confirm roles, deadline, whether a pilot video is wanted, dashboard framework (Streamlit recommended), LLM or templates only, and what to do about the CSVs in git.
2. Person A: download GCAA OMDB charts, run 03, 04, 05; build optimizer (greedy first, then OR-Tools, 3-4 profiles, safety floor); replay across all 5 fog days plus thunderstorm days; diversion balancer; delay-vs-risk chart.
3. Person B: Streamlit dashboard on mock data (alert view, plan comparison, cards, audit log, network map); pitch script and slides.
4. Update both proposals with the new scope decisions (thunderstorms, modular execution, A-CDM integration, option profiles, trade-off chart), using only real numbers.
5. Freeze features, record a backup demo video, rehearse the 3 minutes twice.
Cut list: build first = optimizer, replay, dashboard plan comparison, cards, audit log; balancer as ranked table plus map; LLM and Arabic last; early-warning model, training mode and live integration stay as roadmap.

## 9. Working style and rules
- The user wants short, direct answers without padding.
- Cite exact dataset names, portal, dates and coverage. Label synthetic data and simulated results. Never invent numbers; all demo numbers are indicative.
- API keys in `.env`, never committed. Do not commit or push without being asked.
