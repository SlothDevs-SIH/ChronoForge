# TrueClose: project overview (for the deck and research)

Team Slothdevs: Soham, Ayush, Ishan, Vedashree. ChronoForge hackathon, track **Agentic AI**, theme **Cities of the Future**.
Status when written (24 Oct, morning of the hackathon): the 3-page proposal is done and screened in; the build starts at 10:00. Use the **Status** column in section 12 to know what exists. Do not write "built" on a slide until that column says Done.

---

## 1. One-line definition

**TrueClose verifies that closed civic complaints are actually fixed.**
Tagline: *Closed should mean fixed.*

It is for public grievances filed with a city or municipal corporation: potholes, garbage, streetlights, drains, water leaks, public works. It is not a student or campus grievance tool.

## 2. The problem in plain words

When you complain to a city about a pothole, the complaint eventually shows "Resolved". But:
- The officer who closes the ticket also uploads the proof. Nobody independent checks it.
- Cities and apps rank themselves by **how many tickets are closed**. That rewards closing, not fixing.
- If the citizen doesn't reply, the system reads silence as "satisfied".

Real cases from the proposal (each needs a verified source in the claims register before it goes on a slide):
- **Pune, June 2026:** PMC Care complaints allegedly closed without action; the Standing Committee ordered complainant feedback before closure.
- **Bengaluru:** tickets marked resolved with potholes still open; one complaint reopened 15 times; BBMP added "double escalation" (Sahaaya 2.0).
- **Hyderabad, 2021:** officials reportedly said about 800 of every 1,000 grievances were closed without attending to the issue (say "reported").
- **Mumbai:** average resolution 48 days in 2021, the same as 2017 (Praja).
- **Jalandhar, Swachhata app:** a complaint showed resolved with no action; users uninstalled the app.
- **MGNREGA, July 2025:** the Ministry found identical photos reused across muster rolls and ordered manual verification.
- From Bengaluru's data: road maintenance resolved 58% of the time against 96.4% for electrical (86.2% overall).

## 3. What we are building

An **AI agent layer** that sits on top of any complaint system (it does not replace it). For every ticket marked "resolved" it does this:

```
Ticket closed
  -> 1. SCORE: how likely is this closure to be false? (ML model, gives a % and reasons)
  -> 2. DECIDE: which independent check is worth running next? (the agent, within a cost budget)
  -> 3. CHECK: photo forensics / satellite change / ask the citizen / human spot check
  -> 4. FUSE: combine the evidence into one updated probability
  -> 5. VERDICT: "fixed", "likely not fixed", or "can't tell"
  -> 6. ACT (only with human approval): reopen or escalate on the municipal system
  -> 7. RE-CHECK: later, compare what we predicted with what actually happened
```

Why it is "agentic" and not just a pipeline:
- **Autonomy:** given a ticket, it runs the whole loop itself.
- **Tool use:** it chooses among six tools at runtime.
- **Decisions under uncertainty:** it picks the cheapest useful check, and stops with "can't tell" when evidence is weak.
- **Outcome verification:** it checks whether its own action worked.
- **Safety:** no action without a human approval; everything is logged.

## 4. Who it is for

- **Public:** citizens who file complaints, civic groups and resident associations, NGOs, journalists. They get a short "Was it fixed?" message in their language (Telegram, then WhatsApp) and a public ward-level view of the honest resolution rate.
- **Municipal corporations and government:** commissioner's office, engineering and sanitation departments, IT and smart-city cells, grievance cells, auditors. They get a ranked list of likely wrongly closed tickets, honest metrics and an evidence trail.

## 5. The four checks (what each one does and its limit)

| Check | What it does | Limit |
|---|---|---|
| **Closure score** (ML) | Reads the ticket's data (repeat complaints nearby, how fast it closed, closing time of day, officer batch closing) and gives a probability that the closure is false, with plain reasons | Learned from a proxy label, not true ground truth |
| **Photo check** | Examines the closure photo: reused image? taken near the place and time? does it still show the problem? same place as the original complaint photo? | Public data has no closure photos, so the demo uses a labelled demo photo set |
| **Satellite check** | Compares before/after Sentinel-2 images (10 m per pixel) around the site, against similar nearby places to rule out seasonal change | Cannot see small things like potholes; the agent skips these at zero cost and says so. Runs live on AWS Earth Search; a pre-fetched cache is the fallback and is badged `cached` |
| **Citizen check** | Messages the original complainant "Was it fixed?" and reads the reply in English, Hindi, Marathi or Kannada | No reply is weak evidence, never treated as satisfaction |

## 6. The ML and AI in plain language

**A. Closure-integrity scorer (tabular ML)**
- Models: **LightGBM** plus **logistic regression**, averaged into an **ensemble**, then **calibrated** (so "70%" really means about 70 in 100) with isotonic regression.
- Explanations: **SHAP** turns the model's reasoning into sentences like "3 repeat complaints at this spot in 14 days; closed in 4 minutes".
- Why two models: LightGBM is more accurate; logistic regression is simple and explainable. Averaging usually beats either, and we will show all three results side by side. If the ensemble does not win on the test split we say so and use the better one.
- Features include repeat complaints in the same ~100 m hexagon (H3 index), time to close vs category median, closing hour, officer batch-closing share, ward closing velocity, category base rate, empty closure notes.
- Training label: a ticket counts as a probable false closure if someone complained again at the same place and category within 14 days **after** closure. This is a **proxy**, and we say so. Evaluated with a time-based split (train on earlier months, test on later ones).

**B. Photo verifier**
- **imagehash** (perceptual hashing): fingerprints that match copies of the same photo.
- **EXIF**: location and time stored inside the photo file.
- **CLIP** (an open image-text model): turns a photo into numbers to catch edited/cropped copies and answers "does this still show a pothole?". **DINOv2-small** may be added later for stronger same-scene matching.

**C. Satellite verifier**
- Free **Sentinel-2** images. We compute change indices (vegetation, built-up, bare soil) and a learned change score from our earlier **GEOAI-04** model (U-Net, ONNX).
- Key rigour: compare the site's change to **control places nearby** (a z-score). Raw "change" is meaningless because everything changes with seasons.
- Honest abstention: an eligibility table says which complaint types satellites can and cannot verify.

**D. The agent brain (LLM)**
- An **LLM** (a large language model such as Gemini or an OpenAI model, called over the internet) chooses the next tool, using strict JSON tool-calling. Our code enforces the budget and eligibility, and a rule-based planner takes over if the LLM or the network fails.
- LLM provider order: Gemini (Google AI Studio key), then OpenAI, then the rule-based planner.
- The LLM also writes the plain-language explanation and classifies free-text citizen replies when simple keyword matching cannot.

**E. Evidence fusion (the maths, not a model)**
- Each check returns a **likelihood ratio**: how much more likely this evidence is if the work was not fixed than if it was. We add log-odds: `logit(posterior) = logit(prior) + sum of ln(LR)`.
- Verdict: likely not fixed if posterior >= 0.75; verified fixed if <= 0.25; otherwise "can't tell".
- Assumption to state openly: the checks are treated as independent, which is approximate.

## 7. Data

| City | Source | Real? |
|---|---|---|
| Bengaluru | BBMP grievance records 2020-2025 (OpenCity) | Real (columns are confirmed by Soham in hour one) |
| Pune | PMC open data / published figures | Partial or synthetic; confirmed after the first two hours |
| Mumbai | MCGM/Praja published tables | Partial or synthetic; confirmed after the first two hours |
| Synthetic city | Generated by us, seeded with real category mixes | Synthetic |

Each city in the product shows a badge: `real data`, `partial real data` or `synthetic`. The demo photo set (60 to 100 images with deliberately planted failures: reused photo, wrong location, still-broken) is labelled as demo data. Citizen identifiers are hashed; no raw phone numbers are stored.

## 8. The product (what judges will see)

1. **Ward dashboard:** a city map with a toggle between *Official* and *Honest* resolution rate; the colours shift when toggled. A city switcher shows several cities.
2. **Triage queue:** tickets ranked by probability of false closure.
3. **Ticket detail:** score and reasons, evidence cards (photo, satellite before/after slider, citizen chat) and a **live agent trace** showing which tool it chose and why, a shrinking budget and a moving probability.
4. **Approval queue:** a human approves reopen/escalate, which calls a simulated municipal system.
5. **Citizen page (mobile):** Yes / No / Partly in four languages, plus a public ward view.
6. **Evaluation page:** honest results, with "synthetic injection" labels wherever they apply.
7. **Audit log:** hash-chained, with a "chain intact" check.

## 9. System architecture (for the slide)

Two backend services plus a web app, one repo:
- **Engine service (Soham):** ingest and city connectors, H3 spatial index, DuckDB/Parquet data store, scorer ensemble, satellite verifier, evaluation benchmark, ward statistics, and a simulated municipal endpoint for reopen/escalate.
- **Agent service (Ayush):** photo verifier, agent planner and fusion, Telegram then WhatsApp Cloud channel, approvals, audit log.
- **Web app (Ishan):** React + Vite + TypeScript, MapLibre + deck.gl, live agent trace via server-sent events.

Tech stack: Python, FastAPI, DuckDB, Parquet, H3, GeoPandas, LightGBM, scikit-learn, SHAP, ONNX Runtime, CLIP, imagehash, OpenCV, rasterio, SQLite (Postgres for deployment), React, Vite, TypeScript, Tailwind, MapLibre, deck.gl, Docker, Telegram Bot API, WhatsApp Cloud API.

## 10. What already exists, and our research gap

| System | What its closure check is | Independent of the closing officer? |
|---|---|---|
| CPGRAMS (central grievances) | Call centre contacts citizens after closure; NextGen plans AI validation | Partly; central text grievances, not street-level work |
| Swachhata (Janaagraha) | Inspector uploads "resolved" photo; citizens can reopen; cities ranked by resolution | No; the closer supplies the proof |
| BBMP Sahaaya 2.0 | Double escalation; call-centre reopening after feedback | Depends on citizen persistence |
| GHMC, MCGM Pothole QuickFix | Evidence photo / geo-watermarked photo; 24-hour reopen window | Manual; a photo proves capture, not repair |
| Geo-MGNREGA (NRSC/Bhuvan) | Geotagged before/during/after photos, moderation | Human moderation; rural assets |
| Project DIME (Philippines) | Satellite, drone, LiDAR monitoring | Selected high-value projects only |

**Research gap (draft wording):** every system we found asks the closing officer or the citizen to confirm the fix; we found none that independently verifies the closure with evidence the closer did not supply, combines several evidence types under a cost budget, and can say "can't tell". Vedashree: this is "we found none in our search", not proof of absence. Search Scholar, arXiv and GitHub to confirm, and tell the team at once if a close match exists.

**Our differentiators:** independent evidence, a calibrated score that can abstain, a budgeted agent choosing the cheapest useful check, a citizen in the loop, plug-in municipal connectors, and no auto-penalty path.

## 11. Evaluation (what we will honestly report)

- **Scorer:** AUROC, PR-AUC, Brier score, reliability curve, time-split results, baselines (category rate, one simple rule, logistic regression) vs the ensemble, with confidence intervals.
- **Verifier benchmark:** 1,000 real closed tickets with injected failures (reused photo, shifted location, bulk closing, absent work). Per-check precision, recall, abstention rate, coverage. Always labelled **synthetic injection**.
- **Agent:** cost per ticket vs "run every check on every ticket", and accuracy at equal cost.
- **Human override rate** from the approval queue.
We claim **no real-world false-closure rate**.

## 12. Build status (update this table as things land)

| Component | Owner | Status |
|---|---|---|
| 3-page proposal | Team | Done |
| GEOAI-04 satellite change engine (acknowledged prior component) | Soham | Exists from an earlier project |
| Catalyst AI FastAPI data engines (acknowledged prior component) | Soham | Exists from an earlier project |
| City connectors (Bengaluru, Pune, Mumbai, synthetic) | Soham | Not started |
| Scorer ensemble | Soham | Not started |
| Satellite verifier (live STAC, cache fallback) | Soham | Not started |
| Evaluation benchmark | Soham | Not started |
| Photo verifier | Ayush | Not started |
| Agent planner and fusion | Ayush | Not started |
| Telegram channel, then WhatsApp | Ayush | Not started |
| Approvals and audit log | Ayush | Not started |
| Web app | Ishan | Not started |

## 13. Rules for slides and the pitch

1. Every number needs a source in the claims register. Our own numbers must come from a script we ran.
2. Say "reported" for press figures (Hyderabad ~80%).
3. Label simulated parts: the municipal endpoint is **simulated**; any satellite result served from the fallback cache is badged **cached**; the photo set is **demo data**; benchmark numbers are **synthetic injection**. We have no municipal partnership.
4. **Prior work is acknowledged.** GEOAI-04 and the Catalyst AI engines are earlier projects of ours that we reuse. Slides and README say: "built earlier; the closure-integrity logic, agent, connectors and verification loop are new this weekend." The rules do not allow earlier work to be submitted as new, and judges can see the repo history.
5. Don't name officials or departments as culprits. Talk about systems and incentives.

## 14. Decisions locked (24 Oct)

Multi-city data; demo photos from a labelled demo set; label strategy = proxy plus injected failures; broad scope; DuckDB + Parquet; scorer = LightGBM + logistic ensemble; satellite live via AWS Earth Search STAC with cache fallback; FastAPI; photo = imagehash + EXIF + CLIP (DINOv2-small if time); LLM-chosen tools with Gemini, then OpenAI, then deterministic fallback; Telegram first then WhatsApp Cloud; keyword-then-LLM reply parsing; React + Vite + TS + MapLibre + deck.gl; demo on a laptop and deployed.
Open: colour palette; deck tooling and the citizen survey (Vedashree).

## 15. Where to read more

`00_contract_and_timeline.md` (data contracts, timeline), `backend_soham.md`, `backend_ayush.md`, `frontend_ishan.md`, `research_vedashri.md` (Vedashree's task list, Q&A cheat sheet and reading list).
