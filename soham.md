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
Honest limits until Phase 3: scores are the neutral baseline 0.5, `honest_rate` is null, and the satellite check is a stub (eligibility is real). Phase 3 is the scorer.

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
