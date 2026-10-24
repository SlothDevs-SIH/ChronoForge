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
| **Closure score** (ML) | Bengaluru: a rank score from category, sub-category, ward workload and ward history. Mumbai: one flag, "closed with no attended photo". Synthetic cities: a calibrated probability. Each ticket carries plain reasons | Learned from proxy labels, not true ground truth. See section 6A for what each number means |
| **Photo check** | Examines the closure photo: reused image? taken near the place and time? does it still show the problem? same place as the original complaint photo? | Public data has no closure photos, so the demo uses a labelled demo photo set |
| **Satellite check** | Compares before/after Sentinel-2 images (10 m per pixel) around the site, against similar nearby places to rule out seasonal change | Only for large-area problems (dump sites, nullah corridors, waterlogging over hundreds of metres, large encroachment). Potholes and single garbage piles are "not applicable": the agent skips them at zero cost and says why. Runs live on AWS Earth Search; a pre-fetched cache is the fallback and is badged `cached` |
| **Citizen check** | Messages the original complainant "Was it fixed?" and reads the reply in English, Hindi, Marathi or Kannada | No reply is weak evidence, never treated as satisfaction |

## 6. The ML and AI in plain language

**A. Closure-integrity scorer (tabular ML), as built, with the measured results**
There is no ground-truth "false closure" label in public data, so the scorer works differently in each data regime. This section replaces the earlier plan. The numbers are from `data/models/*.metrics.json`.

| Data | What we ship | What the number means |
|---|---|---|
| **Bengaluru** (real, ward level) | A trained **LightGBM + logistic regression** pair. A rule fixed in advance ships whichever has the best validation score: validation could not separate them (0.734 to 0.737), so **LightGBM shipped, and it is the weakest of the three on the test slice** (logistic 0.64, blend 0.61, LightGBM 0.60). Label: the citizen **reopened** the closure. | A **rank score**, not a probability. Test AUROC about **0.60 to 0.64** (95% CI roughly 0.57 to 0.67); the top 10% of scores hold about **30 to 33% of reopens** (about 3x lift). Category alone gives 0.61. |
| **Mumbai** (real, exact location) | **No trained model.** One rule flag: closed with **no attended photo** (only the citizen's own). | Density-adjusted odds ratio **2.1** (95% CI 1.6 to 2.9; 1.0 to 3.6 on held-out months) that a repeat complaint follows. Small sample (355 tickets). A "closed in under 10 minutes" flag showed **no** effect and is not used. |
| **Pune and Sandbox City** (synthetic) | Trained LightGBM + logistic, isotonic-calibrated, label = injected ground truth. | AUROC about **0.98** on later months and on an unseen city, **because we injected the failures**. Always say "synthetic injection". |

Plain-language findings to use in the deck (all measured on our data):
- **Two leakage traps in Bengaluru's data.** When a ticket is reopened, its staff remark is overwritten ("citizen not satisfied") and it is re-assigned to a senior officer. So remark text and staff role both *reveal* the label. A lookup on staff role alone scored AUROC 0.965, which looked great and was meaningless. We excluded both. Without them the signal is modest, and we report that.
- **The reopen label only exists recently.** Reopen rate is 0.02% in 2020 and about 1.5% in 2025, so the reopen mechanism appears around 2024. We train only on tickets from October 2024 onward, and score older tickets with the neutral 0.5.
- **The Mumbai repeat-complaint label mostly measures how crowded a spot is.** A model using only density reaches AUROC 0.80, and adding every closure feature gives 0.80 again. So we do not ship a Mumbai model, and we are open about why.
- **How the scores reach the agent.** The agent's prior is `p_false_closure`. For real cities it is a *bounded prior* (0.30 to 0.70 for Bengaluru by rank; 0.68 for the Mumbai flag, otherwise 0.5), so evidence decides. Only the synthetic cities carry a calibrated probability (clipped to 0.02 to 0.98).
- **Explanations:** per-ticket **TreeSHAP** reasons from LightGBM (for example "sub-category: water stagnation, ward reopen rate 3%"), or the flag with its measured effect.
- **Do not say:** "our model predicts false closures", "calibrated probability" for any real city, or "AUROC 0.98" without "synthetic".

**B. Photo verifier**
- **imagehash** (perceptual hashing): fingerprints that match copies of the same photo.
- **EXIF**: location and time stored inside the photo file.
- **CLIP** (an open image-text model): turns a photo into numbers to catch edited/cropped copies and answers "does this still show a pothole?". **DINOv2-small** may be added later for stronger same-scene matching.

**C. Satellite verifier (built, narrow by design)**
- Free **Sentinel-2** images (10 m per pixel), read live from AWS Earth Search; a cache makes the demo work offline. Before and after images must come from the **same tile**; "before" is the latest clear scene before the complaint, "after" the earliest clear scene after the closure.
- Key rigour: the site's change is compared with **matched control windows nearby** (places that looked similar before: same vegetation, built-up and brightness), reported as a percentile among the controls. Raw "change" is meaningless because seasons change every pixel. The statistic is undirected: it says the site changed unusually, not what changed.
- **Large-area problems only.** One pixel is 10 m x 10 m, so a pothole or a single garbage pile is invisible. The check applies only when the complaint wording names something spanning many pixels: dump sites, nullah and drain corridors, waterlogging, large encroachment. In our Mumbai data that is **558 of 77,338 tickets (0.7%)**, 291 of them closed. Everything else shows "not applicable".
- **Clouds.** In validation on real ticket dates (April to August, mostly monsoon), about **two thirds of attempts were cloud-obscured** and the check abstained. That is a real limit of optical satellites in Mumbai, and the product says so.
- **How strong is the evidence?** Deliberately weak: an "unusual change" leans "fixed" (likelihood ratio 0.45) and "no unusual change" leans "not fixed" only slightly (1.25), because small works are invisible. These ratios rest on a stated assumption (a real repair changes the site by about 1.5 control spreads) and are **not validated against real repair outcomes: none exist**.
- **What validation shows** (23 measured random locations, wide intervals): with no repair claimed, a site looked unusual 13% of the time (95% CI 3 to 34%) against 10% expected; percentiles were consistent with uniform; an injected change of 1.5 control spreads is found 40% of the time, 2 spreads 65%, 3 spreads 95%.
- **What it found on real tickets:** (the demo-cache run: 71 closed Mumbai tickets with large-area wording, closed mid-April to end of August 2026, live reads with the fixed reader): **46 measured, 25 cloud-obscured, 0 read errors**. Of the 46 measured, **4 (9%) showed unusual change at the site, about the same as the 10 to 13% seen at random places with no repair claimed**; the median site percentile was 0.40, if anything below the controls. So in this sample the closures do not look different from random places. That does not show the work was not done: silt removal and small works are often invisible at 10 m, which is why the evidence is weak. It does mean the satellite check should not be sold as a detector of false closures.
- **Not used:** the learned U-Net from our earlier GEOAI-04 project. It was trained on urban construction change, scores weakly in 3 of its 10 test locations and raises many farmland false alarms, so it is not valid evidence for "was this cleared". Only GEOAI-04's reading conventions are reused (see `engine/app/satellite/NOTICE.md`).
- **Synthetic tickets:** the imagery is real but the ticket is invented, so the result is marked `demo_only` and carries no weight.

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

**Our differentiators:** independent evidence, a score that is honest about what it is (a rank or a bounded prior for real cities) and an agent that can abstain, a budgeted agent choosing the cheapest useful check, a citizen in the loop, plug-in municipal connectors, and no auto-penalty path.

## 11. Evaluation (what we will honestly report)

- **Benchmark v1 (synthetic injection on 1,000 real Mumbai tickets):** 30% marked as false closures with injected symptoms. Instant closures and reused photo ids are caught (recall 1.0, by construction); a photo taken far away is caught 65% of the time (a quarter are deliberately ambiguous); false alarms on clean tickets are 0.7%. The important number: **29% of failures leave no metadata symptom at all**, so only independent evidence (satellite, citizen, human) can catch them. That gap is why the agent exists.
- **Not usable on Mumbai: batch closing.** 28.9% of real closed tickets share a closing minute with 2 or more others closed by the same officer, often kilometres apart (bulk or desk closing), so it is normal and carries no signal. Closing **time of day** and **batch closing** are therefore NOT scorer signals here.
- **Scorer:** AUROC with 95% intervals, PR-AUC, lift in the top 1% and 10%, baselines (constant, category rate, sub-category rate, ward history), always by time split. Bengaluru and Mumbai are real data with proxy labels; the synthetic numbers are labelled synthetic. Full numbers and caveats: `data/models/*.metrics.json`.
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
| City connectors (Bengaluru, Pune, Mumbai, synthetic) | Soham | **Done**: about 822,800 tickets, tested |
| Scorer | Soham | **Done**: Bengaluru rank score (test AUROC about 0.60 to 0.64), Mumbai flag, synthetic calibrated model. Modest, honestly reported |
| Satellite verifier (live STAC, cache fallback) | Soham | **Done**, narrow: large-area problems only, mostly cloud-limited in the monsoon; validated by placebo and injected change, not against real repairs |
| Evaluation benchmark v1 | Soham | **Done** (synthetic injection on real tickets); agent cost-versus-accuracy still needs Ayush's real verifiers |
| Photo verifier | Ayush | **Merged on `integration`**: duplicate, GPS and timestamp checks work on the 12-ticket demo set; CLIP and DINOv2 off and not run with real models, so "still broken" photos are missed |
| Agent planner and fusion | Ayush | **Merged on `integration`**, 96 tests; guarded planner, skeptic, optional LLM planner; ran live against the Engine |
| Telegram channel, then WhatsApp | Ayush | Telegram real and live-verified by Ayush; WhatsApp parked (Meta error). Demo only: needs a registered chat per ticket |
| Approvals and audit log | Ayush | **Merged on `integration`**; approve flows into the Engine and the audit verifies |
| Web app | Ishan, rebuilt 24 Oct | **Done** except the citizen page: landing, how it works, platform (live run), evaluation, overview with ward map and Official/After-reopens toggle, triage, ticket detail with evidence register, approvals, hash-chain audit log. Deployed frontend-only on Vercel (no backend there) |

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

`contract/README.md` (endpoints, fusion rule, rules), `backend_soham.md`, `backend_ayush.md`, `frontend_ishan.md`, `research_vedashri.md` (Vedashree's task list, Q&A cheat sheet and reading list).
