# Soham's workflow (Engine backend)

My job: build the **Engine**, the part that looks at a closed complaint and answers two questions.
1. How likely is it that this closure is false?
2. Can a satellite picture confirm or deny the fix?

Ayush's Agent calls my Engine. Ishan's website shows my results. Details of every feature are in `backend_soham.md`. This file is only the plan: what happens, in what order, on which branch.

---

## Branches

| Branch | Who | What goes in it |
|---|---|---|
| `main` | Everyone | Only code that runs and can be demoed. Nobody works directly here |
| `soham-backend` | Soham | The Engine (`engine/`) |
| `ayush-backend` | Ayush | The Agent (`agent/`) |
| `ishan-frontend` | Ishan | The website (`web/`) |
| `vedashri-research` | Vedashree | Slides, research notes, claims register, screenshots (`docs/`) |
| `integration` | Everyone, mostly Soham | Where the three parts are joined and tested together |

### How code moves
1. Work on your own branch. Commit small and often. Push at least once an hour.
2. When a piece works, open a pull request into `integration`. Another person glances at it.
3. After merging, run all three services together on `integration` and click through the demo.
4. If the demo works, merge `integration` into `main`. Do this before each checkpoint (16:00, 22:00) and before the final.
5. Everyone pulls `integration` into their own branch every couple of hours so nobody drifts.

Rules: never commit `.env` or API keys. Never change a file in `contract/` without telling Ayush and Ishan, because their code depends on it.

---

## The four phases

**Phase 1 status (24 Oct): done.** We have real Mumbai data (121k complaints with coordinates and closing times), real Bengaluru data 2020 to 2025 (767k tickets, ward level only), synthetic Pune on real Pune geography, and a fictional Sandbox City. Read `data/README.md` for the columns, the quirks and the table of plan changes. Biggest change: the plain "repeat complaint after closure" label does not work (see README), so Phase 3 needs a better label.

### Phase 1: Get the data (now to about 11:30)
Goal: real complaint data on my laptop and a list of its columns.

1. Get the Bengaluru (BBMP) grievance files. First try the OpenCity BBMP grievances page. Also search Kaggle for BBMP or Bengaluru complaint datasets (I have not checked whether a good one exists). Download one year, 2024 is fine.
2. Open it with Python or DuckDB. Write down the real column names and the number of rows in `data/README.md`. Post this in the group chat. Everyone's plan depends on what columns exist.
3. Check the key columns: category, ward, latitude and longitude, created time, closed time, status, officer or department.
4. Try Pune and Mumbai the same way. If there is no usable row-level data, we use the synthetic city generator for them. Label every city as `real`, `partial` or `synthetic`.
5. Write the synthetic generator: fake but realistic tickets, with the category mix and published resolution rates of that city.
6. Put raw big files in `data/raw/` (not committed, see `.gitignore`). Commit only a small sample.

Done when: columns are posted, one real file loads, and the synthetic generator makes 1,000 tickets.

**Phase 2 status: done.** All four connectors are built (Mumbai, Bengaluru, Pune, Sandbox), `python -m app.ingest all` loads about 822,800 tickets in 35 seconds, and the API now serves the real tickets from DuckDB over the Parquet files (starts in about 4 seconds; most queries about 0.4 s, a status filter over all of Bengaluru about 2 s). 69 engine tests and 10 agent tests pass. The Agent ran end to end on a real Mumbai ticket. To run it: `cd engine && python -m app.ingest all`, then start the Engine; `/health` shows `mode: warehouse`.
Honest limits: `honest_rate` is still null and the satellite check is a stub (eligibility is real).

**Phase 3 status (scorer): built, with honest results.** Run `cd engine && python -m app.scorer.train all` (about 1 minute). Findings, in the order we hit them:
1. Bengaluru's reopen label is **leaked by two columns**: the remark and the staff role are both overwritten when a ticket is reopened. A staff-role lookup scored AUROC 0.965 and meant nothing. Both are excluded.
2. The reopen mechanism only exists from about 2024, so we train only from October 2024.
3. A time-unit bug (microseconds read as seconds) made every 30-day window decades long. Fixed in `core.epoch_seconds` and covered by tests; the first results were discarded.
4. Bengaluru test AUROC is about 0.60 to 0.64 (top 10% of scores hold about a third of reopens). A rank score, not a probability; calibration made it worse.
5. Mumbai's repeat label is mostly crowding (density-only AUROC 0.80, everything 0.80). No model; one flag, `citizen_image_only`, with density-adjusted OR 2.1 (CI 1.6 to 2.9).
6. Synthetic cities score AUROC 0.98 because we injected the failures; labelled as such.
Numbers and caveats: `data/models/*.metrics.json`.

**Phase 4 status (satellite verifier and benchmark): built. Deployment deliberately NOT done**: we wait for Ayush's backend, then integrate on the `integration` branch, then build the real frontend. What happened:
1. The satellite verifier works end to end on real Sentinel-2 (live check 20 to 40 s; a cache serves the demo). Method and numbers: `data/README.md` ("Satellite verifier").
2. **It applies to very few tickets**: only large-area wording (558 of 77,338 Mumbai tickets; the demo cache covers 71 of them), and cloud blocks 35% of attempts on those tickets (about two thirds in the validation sample, which had more monsoon dates). On the 71 real eligible tickets, 46 were measured and only 4 (9%) showed unusual change, about the same as random places with no repair claimed: the check does not separate closures from random places, so it must not be sold as a false-closure detector. Its evidence is deliberately weak (likelihood ratios 0.45 and 1.25) and not validated against real repairs, because none exist.
3. The validation lost 26% of its runs to **network read errors that were our own load bug**. Fixed (global connection cap, longer retries, no caching of failures); not re-run. Only 23 locations were measured, so the intervals are wide.
4. I did **not** use GEOAI-04's learned model: it detects urban construction change and is not valid evidence for "was this dump site cleared".
5. **Batch closing is normal in Mumbai** (29% of real tickets share a closing minute with 2+ others of the same officer, often kilometres apart), so it is not a signal and was removed. The proposal's "batch patterns" should not be claimed for Mumbai.
6. Benchmark v1 (synthetic injection on 1,000 real tickets): symptoms are caught by construction, but **29% of failures have no metadata symptom** and need independent evidence.
Next: finish the integration, then the frontend.

**Integration status (24 Oct):** Ayush's branch (`ayush`) is merged with mine on the local `integration` branch and verified live together. His 96 tests pass; after integration engine 166 and agent 105 pass. Full details, four fixes I made and the risks are in `INTEGRATION.md`. The most important finding: **on ordinary real tickets the agent has almost no evidence** (no photos, no contacts, 0.7% satellite-eligible), so the closed loop is demonstrable only on the demo set, Telegram-registered tickets and the few satellite-eligible tickets. Open decisions are listed at the end of `INTEGRATION.md`.

### Phase 2: Backend part 1, real data in the API (about 11:30 to 13:30)
Goal: Ishan sees real tickets on his screen instead of fixtures.

1. Write one connector per source (Bengaluru file, Pune, Mumbai, synthetic). Each one turns raw rows into our standard ticket shape.
2. Clean the data: fix dates, drop broken rows, hash officer IDs.
3. Add the map index (H3 hexagons, about 100 m wide) to every ticket.
4. Store everything in DuckDB and Parquet files.
5. Make `/tickets`, `/tickets/{id}` and the city filter read from DuckDB instead of the fixtures.
6. Compute the first simple stats: for each ward, the "official" resolution rate and how many closed tickets got a repeat complaint within 14 days.

Done when: `GET /tickets?city=bengaluru` returns real rows, and I have one real number to give Vedashree before the 16:00 checkpoint.

### Phase 3: Backend part 2, the scorer (about 13:30 to 16:00, then polish to 19:00)
Goal: every ticket gets a "chance this closure is false" score with reasons.

1. Build the features: repeat complaints nearby, time to close, hour of closing, officer closing many tickets at once, empty closure note, and so on.
2. Build the label: a ticket counts as a probable false closure if someone complained again at the same place within 14 days after closing. This is a stand-in, not the truth, and we say so.
3. Split by time: train on earlier months, test on later months.
4. Train two models, LightGBM and logistic regression. Average them. Calibrate the result so that "70%" really means about 70 in 100.
5. Add SHAP so each score comes with plain reasons ("closed in 4 minutes, 3 repeats nearby").
6. Compare against simple baselines so we can show the model actually helps.
7. Replace the fixture scores in `/tickets/{id}/score` with real ones.

Done when: scores come from the model, the test numbers (AUROC and Brier) are printed, and the ward stats show "official vs honest".

### Phase 4: Backend part 3, satellite, benchmark, deploy (about 16:00 to 22:00, fixes after)
Goal: the satellite check works, we can show honest accuracy numbers, and the Engine runs online.

1. Satellite check: find a "before" and "after" Sentinel-2 picture for a ticket's location (AWS Earth Search), cut out a small window, and measure the change. Compare it with similar places nearby so seasonal change does not fool us.
2. Copy in the GEOAI-04 change model and wrap it. Keep a short note that it comes from our earlier project.
3. Skip the checks that satellites cannot do (potholes, streetlights). Return "can't tell, cost 0".
4. Save results for the demo tickets so the demo still works if the internet is slow. Mark each result `live` or `cached`.
5. Benchmark: take 1,000 real closed tickets, inject fake failures (reused photo, wrong location, bulk closing, no work done), and measure how often we catch them. Always label this "synthetic injection".
6. Finish the eval numbers for the evaluation page, then deploy the Engine (Docker, then an online host).

Done when: `/satellite/check` returns real before/after images, `/eval/results` has real numbers, and the Engine runs on a public URL.

---

## Daily rhythm
- **Every hour:** push my branch.
- **At 15:00 and 21:00:** merge into `integration`, run the whole demo, fix what breaks, then merge into `main`.
- **After 22:00:** fix problems the checkpoint showed. Sleep in shifts. Stop adding features at 08:30 tomorrow.

## When I am stuck
- Data has no latitude or longitude: use the ward centre point.
- The satellite call is slow or fails: use the cached result.
- The model scores badly: say so honestly and ship the simple baseline. A true weak number is better than a fake strong one.
- Ask Ayush before changing anything he calls.
