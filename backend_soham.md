# Backend A: Engine service (Soham)

Port 8001. Python 3.11, FastAPI. Read `contract/README.md` first.
Decision points marked **[Qn]** are in `questions.md`. Where I state a lean, it is a recommendation and not a lock.

## 1. What this service is

The Engine answers one question about a ticket: **"how likely is it that this closure is false, and can the sky confirm it?"** It does not decide actions. The Agent service (Ayush) asks the Engine for scores and satellite evidence and decides what to do.

Five modules, in build order:

1. Ingest and connectors
2. Spatial index and feature store
3. Closure-integrity scorer
4. Satellite verifier
5. Evaluation benchmark and ward statistics

## 2. Module 1: Ingest and municipal connectors

### What
A connector turns any complaint source into the canonical `Ticket` (see contract). The proposal promises "municipal system connectors", so this is MVP 2 and has to be real.

### How
```
engine/connectors/
  base.py          # abstract ComplaintSource: fetch(since) -> Iterable[RawRecord]; normalise(raw) -> Ticket
  bbmp_csv.py      # real open data, the primary dataset
  mock_muni.py     # a simulated municipal API that we host ourselves
  telegram_in.py   # tickets filed by citizens via Ayush's bot (posted to /connectors/telegram/sync)
```
- `bbmp_csv`: reads the Bengaluru grievance CSVs (2020-2025, OpenCity). **Hour-zero task: open one file, list the real columns and row counts, and post them in the chat.** Every feature below depends on columns that I have not verified: complaint category, ward, lat/lng (if absent, geocode by ward centroid), created and closed timestamps, status, officer or department field.
- `mock_muni`: a small FastAPI sub-app mounted at `/muni` that mimics what a municipal system exposes: list tickets, get ticket, `reopen`, `escalate`. It is clearly labelled "simulated municipal endpoint" in the UI. It is what the Agent's approved actions actually call, so the loop closes: approve in UI, reopen call, ticket status flips, dashboard updates.
- Anonymise: hash officer and complainant identifiers on ingest. Never store raw phone numbers.

### Options **[Q1, Q2]**
| Option | What | Pros | Cons |
|---|---|---|---|
| A. BBMP CSV only | Real data, one city | Credible, large | Columns unverified, no photos |
| B. BBMP CSV + synthetic photo/closure layer | Real tickets, generated closure evidence for demo | Lets all four checks run end-to-end | Must be labelled synthetic |
| C. B + a second city (Pune/PMC or Mumbai) via scraped open data | Shows generality | Strong scalability story | Time sink, likely thin data |

**DECIDED (Q1, Q2): multi-city.** Bengaluru (BBMP CSV, primary and the only one with a verified-by-us number), plus Pune and Mumbai connectors, plus a synthetic city generator. Each city is one connector class behind the same `ComplaintSource` interface, so the UI can show several city demos. Pune and Mumbai row-level data is not verified to exist: build each as best-effort from whatever public data is found in the first two hours (PMC open data, Praja/MCGM published tables), and fall back to the synthetic generator seeded with that city's real category mix and published resolution statistics. The UI badge per city reads `real data`, `partial real data` or `synthetic`. Closure evidence (photos) is the labelled demo set (Q2 option A).

## 3. Module 2: Spatial index and feature store

- Index every ticket to **H3 resolution 9** (about 100 m edge) and also res 8 for neighbourhood context.
- **DuckDB** is the analytical store (fast on a CSV of millions of rows, zero setup, SQL window functions for repeat-complaint features). App state (approvals, runs) lives with Ayush, so Engine only needs DuckDB plus Parquet files. PostGIS is optional **[Q3]**: only add it if we want server-side radius queries. H3 does the same job with integer joins and costs nothing to run.
- Feature store = a SQL view or Parquet table keyed by `ticket_id`, rebuilt by `POST /connectors/{name}/sync`.

### Features (all computed using only information available at closure time, to avoid label leakage)
| Feature | Meaning |
|---|---|
| `repeat_14d_same_cell` | Open or new complaints in the same H3-9 cell and category in the 14 days **before** closure |
| `repeat_history_90d` | Same, prior 90 days (chronic spot) |
| `time_to_close_h` | Hours between creation and closure |
| `time_to_close_vs_cat_median` | Ratio to the category median |
| `close_hour` | Hour of day of closure (midnight bulk closes are suspicious) |
| `officer_batch_share` | Share of this officer's closures that day stamped within the same 5 minutes |
| `ward_close_rate_30d` | Ward-level closing velocity (pressure to hit targets) |
| `category_base_rate` | Prior false-closure rate for that category |
| `has_closure_note`, `closure_note_len` | Empty or boilerplate notes |
| `reopened_before` | Ticket was reopened earlier |
| `complainant_reopen_count` | If an ID is available, how often this person had to reopen |

## 4. Module 3: Closure-integrity scorer

### The labelling problem (be upfront about it in the pitch)
There is no ground-truth "false closure" label in public data. Options **[Q4]**:

| Option | Label | Pros | Cons |
|---|---|---|---|
| A. Proxy label | Positive if a new complaint appears in the same H3-9 cell and category within 14 days **after** closure | Real data, large n, measurable | Proxy, not truth: a repeat may be a new problem. Must exclude post-closure features |
| B. Injected failures | Take closures, inject known-bad patterns (copy a photo, move the location, bulk-close), train and test on recovery | Clean labels, controlled | Synthetic: it measures detection of what we injected |
| C. Unsupervised | Isolation Forest / autoencoder over the features, rank by anomaly | No labels needed | Hard to explain, hard to calibrate |
| D. A + B | Proxy label for the real-world score, injected failures for the evidence-verifier benchmark | Two honest, separately labelled numbers | More work |

**DECIDED (Q4): D.** Say plainly: "the score predicts probable repeat failure, validated on a proxy; the injected-failure benchmark measures our verifiers."

### Model
- **LightGBM** binary classifier, time-based split (train earlier months, test later months, never random split on time series).
- **Calibration**: isotonic regression on a validation fold. Report reliability curve and Brier score. A calibrated number is what lets the agent do the Bayesian fusion in the contract.
- **Explanations**: SHAP TreeExplainer, top 3 reasons turned into plain language ("3 repeat complaints at this spot in 14 days; closed in 4 minutes; closed at 00:01").
- **Baselines to beat** (this is what makes the number credible): (1) always predict the category base rate, (2) a single rule "repeat_14d >= 1", (3) logistic regression. Show LightGBM vs these in the eval page.
- **DECIDED (Q5): ensemble of LightGBM and logistic regression.** Train both on the same time split, average the probabilities (start 0.6 LightGBM / 0.4 logistic; tune the weight on the validation fold), then calibrate the blended output with isotonic regression. SHAP comes from LightGBM, and logistic coefficients give a second, simpler explanation. Report three rows on the eval page: LightGBM alone, logistic alone, ensemble. If the ensemble does not beat the better single model on the test split, say so and ship the better one. Not chosen: CatBoost, XGBoost, tabular transformers.

### Endpoint
`GET /tickets/{id}/score` returns the Score contract, including `eligible_checks` (which checks can plausibly apply to this category) and `satellite_eligible`.

## 5. Module 4: Satellite verifier (MVP 1)

This is the headline feature and also the riskiest, so the design is built around **honest abstention**.

### What satellites can and can't see
Sentinel-2 is 10 m per pixel. A pothole is invisible. A resurfaced wide road, a cleared dumping site, a filled pond, a new building, or a cleaned drain corridor of about 30 m or more can show up. The verifier therefore has an **eligibility table**:

| Category | Checkable from orbit? | Signal |
|---|---|---|
| Garbage / dumping site (large) | Sometimes | Change in bare-soil / built-up index, NDVI at the site |
| Road resurfacing (wide, arterial) | Weakly | Change in brightness/NIR over the road corridor |
| Encroachment / construction | Yes | Built-up index change |
| Waterbody / drain clearing | Sometimes | NDWI / vegetation change along corridor |
| Pothole, streetlight, small leak | **No** | Return `inconclusive` immediately, cost 0 |

### Pipeline
```
ticket (lat,lng,created_at,closed_at)
  -> buffer polygon (category-dependent radius, 30-150 m)
  -> STAC search for Sentinel-2 L2A scenes: one before created_at, one after closed_at, cloud < 20%
  -> read bands with rasterio (windowed read, no full tile download)
  -> cloud/shadow mask (SCL band)
  -> change features: dNDVI, dNDBI, dBSI, plus the GEOAI-04 learned change score
  -> compare to the distribution of change in matched control polygons nearby (same ward, no complaint) -> z-score
  -> emit Evidence: likelihood_ratio from the z-score, abstain when cloud-obscured or ineligible
```
- **DECIDED (Q6): A, AWS Earth Search STAC (open, no key), live.** The verifier searches Sentinel-2 L2A scenes with `pystac-client` and reads only the small window it needs with `rasterio`. Because a live read can take 10-40 s, we also pre-fetch results for the demo tickets into `data/cache/satellite/` and use the cache as a fallback when the network is slow or down. Every result is badged `live` or `cached`; never call a cached result live. Not used: Planetary Computer, Copernicus, Earth Engine. Sentinel-1 radar stays a stretch goal.
- Sentinel-1 radar (cloud-proof, good for water and large structures) is a **stretch goal**: use the GEOAI-04 flood-mapping path if time allows.
- **Control-polygon z-score** is the key piece of rigour: a raw "change detected" is meaningless because everything changes seasonally. We ask whether this site changed more than similar nearby places did.
- **GEOAI-04 reuse**: the code may be copied into `engine/satellite/geoai04/` and wrapped as `learned_change_score(before_chip, after_chip)`. Keep a short `engine/satellite/geoai04/NOTICE.md` ("derived from our earlier GEOAI-04 project, Fusion hackathon") and list it in the README's prior-work line. The new work, which we claim, is the eligibility logic, the control comparison, the ticket wiring and the likelihood-ratio mapping.
- **Latency**: live and cached paths share the same code and differ only in where the pixels come from. Run the agent's satellite call in the background so the UI shows "checking satellite..." instead of freezing.
- Output `details`: `{before_scene, after_scene, cloud_pct, chip_before_url, chip_after_url, dNDVI, z_score, eligible, reason}`.

### Mapping to a likelihood ratio
Calibrate on the injected benchmark (Module 5): bin the z-score, measure how often "no change" occurs when the work was real vs when it was fake, convert to an LR. Start with a hand-set table (z < 0.5 gives LR 3, z 0.5-1.5 gives 1, z > 1.5 gives 0.3) and replace it with the measured table once the benchmark exists.

## 6. Module 5: Evaluation benchmark and ward stats

### Benchmark generator (`engine/eval/make_benchmark.py`)
- Sample N=1,000 closed tickets. Mark 30% as "failed closures" by injection: (a) the closure photo is reused from another ticket, (b) the closure location is shifted more than 500 m, (c) bulk-closed at the same minute, (d) the work is simply absent (satellite-eligible categories only, using sites with no change).
- Seed everything, store the benchmark file in `data/benchmark_v1.parquet` and commit it so numbers are reproducible.

### Metrics to publish (and display on the eval page)
- Scorer: AUROC, PR-AUC, Brier, reliability curve, time-split results, baselines side by side, 95% bootstrap CIs.
- Verifiers: per-check precision/recall at the verdict thresholds, **abstention rate**, coverage (share of tickets a check could say anything about).
- Agent (computed with Ayush): cost per resolved ticket vs "run every check on every ticket", and accuracy at equal cost. This is the "why agent" proof.
- Ablations: scorer without time features, without repeat features, satellite on/off.
- Always print "synthetic injection" next to benchmark numbers.

### Ward statistics (`GET /wards/stats`)
Per ward and category: **official resolution rate** (share closed) vs **honest resolution rate** (closed minus those with probability of false closure above threshold, plus the unresolved). Also a quiet-ward check: do wards with few complaints wait longer? This is the headline chart for judges and for the public view.

## 7. Stack summary

Decided: Q3 A (DuckDB + Parquet), Q5 ensemble, Q6 A (AWS Earth Search STAC, live with cache fallback), Q7 A (FastAPI).

| Layer | Choice | Not chosen |
|---|---|---|
| API | FastAPI + Uvicorn, Pydantic v2 models generated from the contract | Flask, Litestar |
| Analytics store | DuckDB + Parquet | SQLite, Postgres+PostGIS |
| Geo | H3, GeoPandas, Shapely | PostGIS only |
| ML | LightGBM + logistic regression ensemble, isotonic calibration, scikit-learn, SHAP | CatBoost, XGBoost |
| Satellite | pystac-client + AWS Earth Search, rasterio, ONNX Runtime (GEOAI-04 model), disk cache fallback | Earth Engine |
| Jobs | FastAPI BackgroundTasks, results cached to disk | Celery or Redis (overkill) |
| Packaging | Docker, uv or pip-tools, pytest | |

## 8. Build plan (hour by hour)

| Time | Task | Done when |
|---|---|---|
| 10:00-11:00 | Repo, venv, download one BBMP file, **post real columns**, publish fixture JSON for Ticket, Score, Evidence (satellite) | Fixtures in `contract/` |
| 11:00-12:30 | `bbmp_csv` connector, H3 indexing, `/tickets`, DuckDB tables | Ishan can list real tickets |
| 12:30-14:30 | Features and label (Option A), LightGBM v1, `/score` | AUROC printed, even if mediocre |
| 14:30-16:00 | `/wards/stats`, mock municipal endpoint, **first real number for Round A** (for example, "X% of closed tickets had a repeat within 14 days") | Number given to Vedashree before 15:30 |
| 16:00-19:00 | Satellite verifier: Earth Search STAC read, indices, control z-score, GEOAI-04 code copied in, cache for demo tickets across cities | `/satellite/check` returns real before/after chips |
| 19:00-21:00 | Benchmark generator, calibration, SHAP text, baselines, `/eval/results` | Eval page has real data |
| 21:00-22:00 | Bug bash with Ayush's agent end to end | Round B demo |
| 22:00-02:00 | LR calibration from benchmark, error analysis, perf, Dockerfile | Deployed |
| 07:00-09:00 | Freeze, only fixes | |

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| BBMP file lacks lat/lng or closure timestamps | Fall back to ward-level indexing and timestamp-only features; use whichever columns exist and tell Vedashree immediately so slides match. Backup: another city's open data or the synthetic generator |
| STAC is slow or down during the demo | Pre-fetched disk cache as automatic fallback, with a visible "cached" badge |
| Proxy label is criticised | We say it is a proxy and publish the injected-failure benchmark separately |
| Satellite shows nothing for most categories | That is expected and by design; headline claim is "right check for the right claim, abstain otherwise" |
| GEOAI-04 model wrapper breaks | The index-based features (dNDVI, dNDBI) work without it; the learned score is an add-on |
| Leakage inflates AUROC | Time-based split plus a feature audit table in the README |

## 10. Interface checklist for Ayush
- [ ] `POST /satellite/check` returns Evidence in under 3 s from cache and under 60 s live
- [ ] `GET /tickets/{id}/score` is idempotent and fast (under 200 ms)
- [ ] `/muni/tickets/{id}/reopen` flips status and writes a row Ayush can see via `GET /tickets/{id}`
- [ ] The benchmark file is shared so his photo verifier is scored on the same tickets
