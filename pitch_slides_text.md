# DABAB pitch: slide text (3 minutes)

Order and timing (180 s): Video 10 · Problem 20 · Solution & alignment 20 · Team 12 · Live demo 48 · AI 15 · Results 10 · Business model canvas 5 · Business key points 12 · Feasibility & 90 days 20 · Close 8.
Challenge: **Challenge Profile #3 · GCAA**, under the themes **Responsible AI & Smart Cognitive Government · Aviation Safety · AI-Enabled Innovation**.
Every number below comes from our data or engine. "Simulated" numbers must stay labelled.

---

## 0. Video hook (0:00–0:10)
*No slide. Play the 10-second video.*

---

## 1. Problem (0:10–0:30)

**Kicker:** THE CHALLENGE · GCAA CHALLENGE PROFILE #3

**Title:** When fog hits Dubai, controllers re-plan dozens of flights by hand, in minutes

**Big number (left):** **86 min**
average arrival delay in fog at DXB, vs **11 min** on normal days

**Three points (right):**
- **Capacity collapses:** on 3 Jan 2026, visibility fell to 193 m and landings dropped from 28 to 15 an hour.
- **Systems don't talk:** air navigation, the airport and airlines each see only their part of the picture.
- **Trade-offs are hidden:** less delay can mean more fuel burned holding; no one sees the cost of each choice.

**Small table (optional):**
| Weather at DXB | Events | Avg delay vs normal | Flights >15 min late |
|---|---|---|---|
| Fog | 5 | 86 vs 11 min | 83% vs 28% |
| Thunderstorm | 2 | 102 vs 15 min | 81% vs 33% |

**Footer:** Data: Dubai Airports flight information, 282,705 arrivals (May 2025 – Nov 2026), Data.Dubai · OMDB METAR

**Speaker notes:** "That morning was real. On 3 January, fog closed Dubai International. Across 18 months of Dubai Airports data, fog days average 86 minutes of delay, against 11 on normal days. Controllers decide who holds, who diverts and where, by hand, with three systems that don't talk."

---

## 2. Solution, alignment and data (0:30–0:50)

**Kicker:** THE SOLUTION

**Title:** DABAB: the AI predicts, plans and explains. The human decides.

**Journey (5 steps, left to right):**
1. **Predict:** AI fog model raises a Watch hours before the fog.
2. **Prioritise:** the controller chooses: less delay, less fuel, fewer diversions or protect connections.
3. **Plan:** three ranked recovery plans in seconds: landing order, holds, diversions, stands.
4. **Explain:** why this plan, what it costs, why not the others, in Arabic and English.
5. **Decide:** the controller approves, modifies or rejects; one message goes to tower, airport, airlines and cockpit. Every decision is logged.

**Badge row (top of slide):** GCAA · Challenge Profile #3 · themes: **Responsible AI & Smart Cognitive Government** · **Aviation Safety** · **AI-Enabled Innovation**

**Strip: "Built for the challenge"** (tick list, the challenge's own words):
- ✓ Immediate, accurate, reliable decisions: plans in seconds, reliability shown on every plan
- ✓ Allocating landing stands: 220 official DXB stands, aircraft size enforced, zero stand conflicts
- ✓ Integration between air navigation and airport systems: one approved plan, shared by tower, airport, airlines
- ✓ AI and real-time operational data: fog prediction, optimizer, grounded LLM, live METAR
- ✓ UAE direction: National Strategy for AI 2031, digital government, safer and greener aviation

**Strip: "How DABAB maps to the three themes"** (three small boxes):
- **Responsible AI & Smart Cognitive Government:** human approves every plan; explanations grounded in engine facts; every decision logged; shared picture for government operators (GCAA, dans, Dubai Airports)
- **Aviation Safety:** hard safety rules never relaxed: fuel reserve with 5-min buffer, ILS minima at alternates, stand size, A380 limits
- **AI-Enabled Innovation:** ML fog prediction + optimizer + grounded LLM, working on real UAE open data

**Strip: "Government open data"** (three logos or names):
**Data.Dubai** (Dubai Airports: 282,705 arrivals) · **GCAA eAIP** (220 stands, runways, ILS for 7 UAE airports) · **METAR** (7 UAE airports since 2014)

**Speaker notes:** "This is GCAA's Challenge Profile 3, under Responsible AI, Aviation Safety and AI-enabled innovation. DABAB is a decision copilot for controllers. It warns before the fog, builds three recovery plans in seconds, explains each in Arabic and English, and a human always approves. It answers the challenge line by line, and it runs on government open data: Dubai Airports flights, the GCAA aeronautical publication and airport weather reports."

---

## 3. Team, motivation and progress (0:50–1:02)

**Kicker:** THE TEAM

**Title:** Two builders, one working system on real data

**Left: team**
- **Ali Eissa**, engine and AI: data pipeline, fog model, optimizer, grounded explanations, backend
- **Mohammed Hishaam**, product and pitch: ATC decision panel, user journey, business model

**Middle: motivation (one line)**
"Fog is the UAE's most disruptive weather for aviation, and the decision is still made by hand."

**Right: progress (from wireframe to working system)**
- Low-fidelity wireframe → working ATC panel with live backend *(show wireframe image for 3 seconds)*
- 282,705 real arrivals analysed; 220 GCAA stands mapped (98% of arrivals matched)
- Fog model trained on 12 years of METAR
- Engine replays real fog mornings (3 Jan and 10 Feb 2026)

**Speaker notes:** "We are two people. In this hackathon we went from a paper wireframe to a working system on real data." *(Switch to the dashboard.)*

---

## 4. Live dashboard demo (1:02–1:50)
*No slide. Switch to the dashboard. Click path, about 10 s each:*

1. **Header:** "The AI fog model raised a Watch at 01:30, five and a half hours before fog hit at 07:04. On the right, the real weather reports from that morning."
2. **Profiles:** click *Minimum fuel*. "The controller chooses the priority. Safety rules never change."
3. **Plans:** "Three plans, each with delay, diversions, fuel, connections and reliability. In our replay, against no coordination, the recommended plan cuts holding and diversion fuel by 37% and the risk index by 24%."
4. **Explain:** click plan C. "Why this plan, what it costs, why not the others: written by the AI, using only the engine's numbers."
5. **Approve:** click *Approve*. "One click sends the plan to tower, airport stands, airline ops and the cockpit, and it's logged. The human decides." *(Optional: toggle Arabic for 2 s.)*

---

## 5. Innovative use of AI (1:50–2:05)

**Kicker:** THE AI

**Title:** Three AI layers, each one checkable

**Three columns:**
- **Predict: fog model (machine learning).** Gradient-boosted model trained on 12 years of METAR from 7 UAE airports. Warned of **95% of fog events** in unseen test data, with a median of **4 hours** notice. On 3 Jan: **5 h 34 min** before the fog.
- **Plan: optimizer.** Re-sequences 185 arrivals, holds flights on the ground at origin, balances diversions across UAE airports by weather, A380 limits and capacity. Hard safety rules: fuel reserve, stand size, ILS minima.
- **Explain: grounded LLM.** Writes the explanation in Arabic and English. Every number it writes is checked against the engine; one invented number and it is rejected for a template.

**Bottom line:** Responsible by design: the human approves every plan; every decision is logged.

**Speaker notes:** "Three AI layers: a fog prediction model, an optimizer with hard safety rules, and a language model that explains, but can only quote numbers the engine produced."

---

## 6. Results (2:05–2:15)

**Kicker:** THE IMPACT

**Title:** Replaying real fog mornings: same safety, less fuel, fewer diversions

**Four big numbers (in our replay of 3 Jan 2026, vs no coordination, same simulation):**
- **−37%** holding and diversion fuel (335 t → 212 t)
- **−24%** risk index
- **−40%** diversions (10 → 6, minimum-diversions profile)
- **5 h 34 min** fog warning before the fog

**One line under it:** Validated: on 10 Feb 2026 the no-coordination simulation reproduces the real day (28 vs 28 diversions; 56.9 vs 57.2 min delay).

**Footer:** Simplified simulation on real flights, weather and stands; fuel reserves and connecting passengers are synthetic. Indicative, to be confirmed in the 90-day trial.

**Speaker notes:** "In our replay of the real 3 January morning, DABAB's plan used 37% less holding and diversion fuel than an uncoordinated plan in the same simulation, and cut risk by a quarter. The flights, weather and stands are real data; the simulation reproduced a real fog day, 10 February, almost exactly. So we present these as indicative results, and the 90-day plan is how we prove them with controllers."

*If a judge asks "are these real?":* "The weather, flights and stands are real government data. The fog model was tested on years it never saw. The plan savings come from a simulation that reproduced a real fog day almost exactly, so we present them as indicative."

---

## 7a. Business model canvas (2:15–2:20)

**Kicker:** THE BUSINESS MODEL

**Title:** DABAB business model canvas

**Full-slide canvas** (rebuild the 9 blocks as a grid, short text only):
| Key partners | Key activities | Value proposition | Relationships | Users and customers |
|---|---|---|---|---|
| GCAA (regulator, sponsor, eAIP) · dans (air navigation) · Dubai Airports (AODB, stands, A-CDM) · airlines · NCM (weather) · Digital Dubai (open data) · TDRA | Keep flight, METAR and stand feeds live · tune optimizer and safety rules with controllers · replay every weather day · keep AI explanations grounded | Ranked recovery plans in seconds instead of manual juggling · delay, fuel, CO₂, diversions, reliability per plan · Arabic and English reasons · human approves, everything logged · one shared picture | Co-designed with controllers · shadow mode first · approve / modify / reject builds trust · review after each weather event | **Users:** approach and tower controllers, supervisors, airport and airline ops centres · **Payers:** dans (under GCAA); airports co-buy · **Later:** UAE and Gulf airports |
| | **Key resources:** open data (Data.Dubai, GCAA eAIP, METAR) · engine, fog model, LLM, panel · engineer, product lead, ATC advisor | | **Channels:** GCAA-led pilot at DXB · layer on A-CDM (AODB, METAR feeds) · then other UAE and Gulf airports | |

| Costs | Revenue and funding |
|---|---|
| Integration with A-CDM / AODB / ATC systems (largest) · safety assurance · controller time in the pilot · hosting and small LLM usage | Annual licence per airport (SaaS) + one-off integration and training · GCAA / TDRA-sponsored pilot first · savings: holding fuel, diversions, missed connections, CO₂ |

**Speaker notes:** *(say nothing new; go straight to the next slide)* "Here is the full model; the next slide has the three points that matter."

---

## 7b. Business key points (2:20–2:32)

**Kicker:** MARKET POTENTIAL

**Title:** Who pays, how it reaches them, why it scales

**Three columns:**
- **Who pays:** dans, Dubai's air navigation provider, under GCAA. Airports co-buy; airlines benefit from fewer diversions and missed connections.
- **How we earn:** annual licence per airport (SaaS) plus one-off integration and training. First year funded as a GCAA / TDRA pilot.
- **How it scales:** DXB first, then the 6 other UAE airports with the same engine, then fog-prone Gulf airports. Each new weather event improves the model.

**Value line (big):** One fog morning at DXB: about **123 t of holding fuel** saved in our replay (**≈390 t CO₂**).

**Footer:** Fuel saving from the 3 Jan 2026 replay vs no coordination (simplified simulation).

**Speaker notes:** "The air navigation provider pays an annual licence per airport, with airports as co-buyers. We start at DXB and scale to every UAE airport with the same engine. In our replay, one fog morning saved about 123 tonnes of fuel; we will confirm real savings in the trial."

---

## 8. Feasibility (2:32–2:40)

**Kicker:** FEASIBILITY

**Title:** It already runs. What remains is integration and approval.

**Two columns:**

**Already built and working (proof)**
- Data pipeline on real government open data: 282,705 arrivals, 220 GCAA stands, 7 airports
- Fog model trained and tested on unseen data (95% of fog events warned)
- Engine replays two real fog mornings; validated against the real 10 Feb outcome
- Working ATC panel with backend, audit log and hand-off message

**What it needs (and why it is realistic)**
- **Data access:** live Dubai Airports API (already requested on Data.Dubai) and an NCM METAR feed
- **Integration:** read-only links to A-CDM / AODB first; DABAB only advises, so existing systems are unchanged
- **Approval:** GCAA safety case for a suggestion-only trial
- **Team:** 2 builders + 1 ATC advisor from dans + GCAA sponsor

**Risks and mitigations (one line each):**
Controllers don't trust it → shadow mode and drills first · data access is slow → replay and simulation keep testing going · safety concerns → advisory only, human approves every plan

**Speaker notes:** "Most of the hard part already works on real data. What remains is data access, read-only integration and GCAA approval, and DABAB only advises, so nothing in today's systems has to change."

---

## 9. 90-day plan (2:40–2:52)

**Kicker:** THE PATHWAY

**Title:** 90 days: from prototype to a GCAA go / no-go

**Timeline (three phases, each with deliverables and a measurable exit test):**

**Days 1–30 · Secure and compliant**
- Wk 1–2: rebuild codebase with code review, automated tests, CI; access roles; encrypted, signed audit log
- Wk 3: UAE data residency hosting; privacy and security review
- Wk 4: safety case outline following aviation software assurance practice (DO-278A / ED-109A)
- **Exit test:** security review passed · 100% of engine tests pass · zero safety-rule violations in all replays

**Days 31–60 · Beyond fog, open to other systems**
- Wk 5–6: live Dubai Airports API + NCM METAR feed; retrain fog model on new data
- Wk 6–7: add thunderstorm and dust events using the same engine (2 storm days already in our data)
- Wk 7–8: secure execution endpoint: external systems, including AI, can apply **only human-approved** plans (signed approval, read-only by default)
- **Exit test:** fog model warns ≥ 90% of events ≥ 2 h ahead on new data · endpoint works end to end in a sandbox

**Days 61–90 · Test, simulated then real**
- Wk 9–10: replay every fog and storm day since 2025; report fuel, delay and diversions vs what happened
- Wk 11: fog drills with 5+ controllers in a simulator; collect approve / modify / reject decisions
- Wk 12: with GCAA approval, shadow mode at DXB (suggestions only, no live control); otherwise extended simulation
- **Exit test:** controllers accept ≥ 70% of recommended plans in drills · measured fuel saving on every replayed day · GCAA go / no-go decision

**Speaker notes:** "Ninety days, three phases, each with a measurable exit test. First make it secure and compliant. Then connect live data, extend it beyond fog, and open a secure endpoint so other systems can apply approved plans. Then test it: every past weather day, drills with controllers, and shadow mode at DXB if GCAA approves."

---

## 10. Closing (2:52–3:00)

**Title:** When the weather changes, nobody should have to guess.

**Subtitle:** DABAB: the AI predicts, plans and explains. The human decides.

**Footer:** Ali Eissa · Mohammed Hishaam · TDRA Hackathon 2026 · GCAA Challenge Profile #3

**Speaker notes:** "Fog will come back to Dubai. With DABAB, the next time, the plan is ready before the fog is. Thank you."
