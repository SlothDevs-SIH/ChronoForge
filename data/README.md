# Data notes (Phase 1, complete)

Raw files live in `data/raw/` and are **not committed** (see `.gitignore`). Small processed files in `data/processed/` and the scripts in `data/scripts/` are committed.

## What we have

| City | Source | Rows | Real? | Coordinates | Closing time | Reopen / escalation | Photos |
|---|---|---|---|---|---|---|---|
| **Mumbai** | BMC MARG public ArcGIS service, layers 0 and 16 | 121,331 complaints + 12,492 potholes | **Real** (live snapshot, 18 Mar to 24 Oct 2026) | Yes, per complaint | Yes: `AFTER_IMAGE_DATE` (60,300 valid closed tickets); `RESOLVED_DATE` (potholes, all resolved) | Escalated flag; pothole reopen (27 tickets). Complaint-layer `REOPEN` is empty | File names only, no images |
| **Bengaluru** | OpenCity BBMP grievances 2020 to Jun 2025 (six yearly CSVs) | 766,648 | **Real** | Ward centroid only (98.3% of tickets, via ward map) | **No** | `ReOpen` status (918 in 2024) | None |
| **Pune** | No complaint data is public. Real Pune wards and drain lines only | 5,904 | **Synthetic complaints on real geography** | Yes (generated) | Yes (generated) | Generated | Photo ids only |
| **Sandbox City** | Fully fictional | 5,883 | **Synthetic** | Yes (generated) | Yes (generated) | Generated | Photo ids only |

## Files

```
data/raw/                        (not committed)
  bbmp_2020.csv ... bbmp_2025.csv           OpenCity BBMP grievances
  mumbai_marg_complaints.csv                BMC MARG layer 0 (safe fields only)
  mumbai_marg_potholes.csv                  BMC MARG layer 16 (safe fields only)
  bengaluru/bbmp_wards_2015.kml             198 ward polygons
  pune/pune_wards_2022.kml, pune_nalla_map.kml, pune_swd_chambers.kml, pune_streetlights_by_ward.csv
data/processed/                  (committed)
  bengaluru_wards.csv                       ward centroids from the 198-ward map
  bengaluru_ward_name_map.csv               complaint ward name -> boundary ward (exact 130, fuzzy 63, manual 3, unmapped 2)
  pune_wards.csv, synthetic_wards.csv       ward centroids
  synthetic_pune.csv, synthetic_city.csv    generated tickets with gt_* ground-truth columns
data/scripts/
  download_mumbai.py                        re-download Mumbai (read-only queries, safe fields only)
  make_synthetic.py                         regenerate synthetic cities (seeded, deterministic)
```
To rebuild: `python data/scripts/download_mumbai.py` then `python data/scripts/make_synthetic.py`. The BBMP and Pune files come from OpenCity (links below).

## Mumbai (strongest real dataset)
Source: BMC "MARG" public map service, `https://marg.mcgm.gov.in/server/rest/services/MARG_APP/MARG_Application_Prod/MapServer`, layers 0 (complaints) and 16 (potholes). Found via the open-source project metaloozee/city-problems-mumbai, then checked directly.

- **Licence:** BMC states no explicit open-data licence for this service. Use for the hackathon prototype with attribution to BMC/MCGM. Check with BMC before any wider or commercial reuse.
- **Privacy:** we deliberately did not download citizen contact fields, user ids, names, addresses, landmarks or free-text descriptions. Staff ids are hashed in the download script.
- **Complaints (layer 0):** 88,261 CLOSED, 14,997 DISCARDED, 12,389 IN PROGRESS, 5,213 IN REVIEW, 471 NEW. 26 wards. 1,510 distinct (hashed) ground-staff ids. Sources: MyBMC MARG 57k, helpline 1916 25k, X 21k, WhatsApp 13k, web 6k.
- **Closing time:** only 1,730 closed rows have `RESOLVED_DATE`. Use `AFTER_IMAGE_DATE` as the closing time instead (60,300 valid closed rows). Per another project's documentation it is the date of the attended image, so it is a proxy for closure, not a formal closing timestamp. Median time to close is 207 h, 90th percentile 1,793 h; 60 tickets closed within 10 minutes.
- **Potholes (layer 16):** 12,492 records from 30 May 2026. 12,298 Resolved; 4,783 marked Invalid; 7,515 valid and resolved. Median 44.8 h to resolve, 90th percentile 133 h. `CONFIRM_POSTWORK_IMAGE` flag set on 6,506 of the 7,515. Reopen: 27.

### Quirks to handle in the connector
1. **15,526 complaints share one placeholder coordinate** (19.07766361, 72.87740978). Drop them or flag them; they are not real locations.
2. `INVALID = YES` (27,935) means the complaint was judged invalid. Exclude from scoring; 20,663 have no value.
3. `REOPEN` in layer 0 is empty for every row. Reopen signal exists only for potholes (27).
4. `ESCALATED_NEW = YES` on 61,498 rows (half). We do not know what triggers it; do not present it as a failure signal until understood.
5. Image columns hold file names only (we cannot fetch images). `AFTER_IMAGE` listing only "Initial Image By Citizen.jpg" on a closed, valid ticket means no attended photo was uploaded: **383 such tickets** (0.6%). 57,118 closed valid tickets do have an "Attended" image. A real, rare closure-integrity signal.
6. The live service keeps changing; our snapshot is dated 24 Oct 2026.

### Mumbai connector (Phase 2, built)
Code: `engine/app/connectors/mumbai.py` (interface in `base.py`), run with `cd engine && python -m app.ingest mumbai`. Writes `data/warehouse/tickets_mumbai.parquet` (gitignored) and a drop report. Tests: `engine/tests/test_mumbai_connector.py` (use small built-in fixtures, no raw data needed).
- **Result on our snapshot:** 121,341 rows read, **77,338 kept**: 60,029 closed, 17,283 open, 26 reopened. Dropped: discarded 14,997; invalid 27,978; outside Mumbai 475; placeholder location 518; closed before created 5; closed without time 22; missing ward 7; missing coordinates 1. (Most of the 15,526 placeholder-location rows were already invalid or discarded, hence only 518 under that reason.)
- **Categories** (by complaint name, not type): other 38,642; garbage 14,082; drain 11,356; pothole 10,924 (includes road re-surfacing, since the contract has no separate road-repair category); water leak 1,461; streetlight 873. "Encroachment ... footpath / drains" is deliberately `other`, not drain.
- **Pothole layer** enriches matching tickets (real resolved date, post-work photo flag, reopen) instead of adding duplicate rows; 10 pothole-only rows are added.
- **Reopen:** 26 reopened tickets, all potholes. A reopened ticket is usually no longer "Resolved", so reopen is read independently of the closed status.
- **Extra signal columns** beyond the contract: `has_attended_image`, `citizen_image_only` (369 closed tickets after drops), `escalated`, `channel`, `closing_basis`, `res_hours`, `zone`, `complaint_type`, `from_pothole_layer`.
- **Known quirk:** 432 groups of 5 or more identical complaints in the same 100 m cell on the same day. Could be bulk filing or duplicates. Matters for any repeat-complaint feature.
- `lang` is `other` (the language field was not downloaded), `text` is the complaint name (free text deliberately not fetched), `closure_photo_url` is empty (file names only).

## Bengaluru
Source: OpenCity, https://data.opencity.in/dataset/bbmp-grievances-data (public domain, one CSV per year).
- Columns: `Complaint ID, Category, Sub Category, Grievance Date, Ward Name, Grievance Status, Staff Remarks, Staff Name`.
- 2024: 207,016 rows, no empty values, 198 wards, 835 staff names. Status: Closed 190,171; Non Relevant 9,123; Registered 6,269; ReOpen 918; In Progress 357; Long Term Solution 178.
- Top categories: Electrical 75k, Solid Waste 57k, Road Maintenance 25k, Health 15k. Top sub-categories: Street Light Not Working 71k, Garbage vehicle not arrived 21k, Garbage dump 20k, Potholes 6k.
- Staff remarks on closed tickets are mostly boilerplate ("Attended", "Resolved", "Cleared"); 1,634 are just ".".
- **Missing:** latitude/longitude, closing date/time, photos, complainant id. Only the creation date exists.
- **Ward centroids:** the 2015 ward map (198 wards) matched 98.3% of tickets by name: exact 130 wards, fuzzy 63, manual 3. **Unmapped: Subedarapalya and Someshwara** (Someshwara alone is about 11k tickets). A person should check these two against the ward map before relying on them.
- Fuzzy matches were spot-checked: weakest pairs look plausible (Ulsoor to Halsoor is Halasuru). Confirm the fuzzy column if ward-level accuracy matters.

### Bengaluru connector (Phase 2, built)
Code: `engine/app/connectors/bengaluru.py`. Run `cd engine && python -m app.ingest bengaluru` (about 25 s).
- **Result:** 766,648 rows read, **733,721 kept**: 708,831 closed, 22,191 open, **2,699 reopened** (matches the raw `ReOpen` count). Dropped: Rejected 16,803; Non Relevant 16,050; null status 74. No duplicate ids across the six years.
- **Status mapping:** Closed and Resolved are closed; ReOpen is reopened; Registered, In Progress and Long Term Solution are open.
- **Categories:** streetlight 298,547; garbage 204,439; other 169,399; drain 33,061; pothole 28,275. By sub-category: "Street Light Not Working" and day-time/park lights are streetlight (new-light requests are `other`); "Potholes" is pothole; road-side drains, water stagnation and SWD items are drain; solid waste and debris removal are garbage.
- **Location:** `location_precision` is `ward_centroid` for 721,165 tickets and `none` for 12,556 (Someshwara 10,634; Subedarapalya 1,920; "NON Ward" 2). `h3` is always null and `closed_at` is always null, because the source has neither. These tickets must not feed satellite checks or 100 m repeat features.
- **Time:** the source dates are naive local time. We treat them as IST and convert to UTC (assumption). Range 7 Feb 2020 to 19 Jun 2025.
- **Staff:** names are hashed (`closed_by_hash`); the role after "/" is kept as `staff_role` (AEE 473k, JHI 56k, AE 51k, DYRFO 29k, MOH 23k).
- **Remarks:** on non-open tickets the remark is kept as `closure_note`, with `remark_norm` (lower-cased text) and `remark_blank_like` (2.8% are blank or a single character). Boilerplate dominates: "attended" 301k, "resolved" 97k, "cleared" 42k, "closed" 28k, "clear" 23k.
- **Data quality:** `partial`.

### Synthetic connector (Phase 2, built)
Code: `engine/app/connectors/synthetic.py`. Run `python -m app.ingest pune` and `python -m app.ingest synthetic`.
- Pune: 5,904 tickets. Sandbox City: 5,883 tickets. Every ticket is `data_quality="synthetic"` with `location_precision="generated"`.
- **Ground truth is separated by construction.** Tickets never carry `gt_*`. Truth goes to `data/warehouse/truth_pune.parquet` and `truth_synthetic.parquet` (1,199 and 1,175 false closures). Only the benchmark may read those files.
- Extra columns: `closure_photo_id`, `closure_photo_exif_dist_m`.

### The store and the API (Phase 2, built)
`engine/app/store.py`: `WarehouseStore` loads the Parquet files into DuckDB (about 4 s for 822,846 tickets). Status changes from the simulated municipal system (reopen) live in a small `status_overrides` table joined into a view, so lists, filters and ward stats always agree. `FixtureStore` (the six contract fixtures) is the fallback when no warehouse exists; `ENGINE_DATA_MODE=fixtures|warehouse|auto` forces a mode.
- **Scores:** `engine/app/scoring.py` returns the neutral baseline (0.5, `baseline-no-model`) until Phase 3.
- **Satellite eligibility** (`engine/app/eligibility.py`): only garbage and drain tickets with an `exact` or `generated` location. Everything else is skipped at cost 0, including every Bengaluru ticket.
- **Real numbers from the API today:** Mumbai 77,338 tickets (60,029 closed, 26 reopened); Bengaluru 733,721 (708,831 closed, 2,699 reopened); Pune 5,904 and Sandbox 5,883 synthetic. Example: Begur ward potholes, 1,426 tickets, 99.7% no longer open, 5 reopened.
- The recent Mumbai tickets are mostly open (the data is a live snapshot), so use `status=closed` when listing tickets to check.

### Scorer (Phase 3, built)
Code: `engine/app/scorer/` (`core.py` shared machinery, `features_*.py` per city, `train.py`, `runtime.py` for per-ticket reasons). Run `cd engine && python -m app.scorer.train all`. Metrics with full caveats: `data/models/*.metrics.json` (committed, with the small model files).
- **Bengaluru** (`blr-reopen-v1`): label = status ReOpen, tickets from 1 Oct 2024. Split: train before Mar 2025 (1,306 reopens), validate Mar to Apr (357), test May onward (639 reopens). Features: category, sub-category, ward zone, hour, weekday, ward workload (30 days), ward and sub-category history (14 and 90 days), ward and sub-category reopen rate lagged 30 days. **No remark or staff features** (both leak: a reopened ticket gets a new remark and a senior handler). Test AUROC: LightGBM 0.596, logistic 0.643, blend 0.614; category-rate baseline 0.610. Top-10% lift about 3.0 to 3.3.
- **Mumbai** (`mum-flags-v1`): no model. Label (repeat in the same 100 m cell and category, 24 h to 14 days after closure) is mostly crowding. Flag `citizen_image_only`: density-adjusted odds ratio 2.11 (95% CI 1.58 to 2.86), held-out months 2.12 (1.04 to 3.55). `fast_close`: odds ratio 0.99, no effect.
- **Pune and Sandbox** (`syn-truth-v1`): trained on Pune, tested on later Pune months (AUROC 0.982) and the unseen Sandbox city (0.981). Synthetic injection.
- **Selection rule** (fixed before looking at test): ship whichever of LightGBM, logistic or blend has the best validation AUROC. For Bengaluru that is LightGBM, although logistic did better on test; validation could not separate them.
- **Priors:** Bengaluru 0.30 + 0.40 x rank percentile; Mumbai 0.5, or 0.678 when flagged; synthetic clipped to 0.02 to 0.98.
- **Found and fixed on the way:** both leakage traps; the structural-zero period before the reopen mechanism existed; a microsecond-as-second time bug that made every window decades long (first results discarded); isotonic calibration that made a drifting label worse.

### Satellite verifier (Phase 4, built)
Code: `engine/app/satellite/` (`reader.py`, `scenes.py`, `change.py`, `verifier.py`, `validate.py`, `precompute.py`; `NOTICE.md` credits GEOAI-04's conventions). Metrics with caveats: `data/models/satellite.metrics.json`.
- **Method:** same-tile before and after Sentinel-2 scenes (before = latest clear scene before filing, after = earliest clear scene after closing, within 60 days); one 3.2 km window per scene; 60 matched control windows (matched on pre-change NDVI, NDBI, brightness); change magnitude over NDVI, NDBI, NDWI and brightness differences, reported as a percentile among the controls. "Unusual change" means above the 90th percentile of the controls. It abstains on cloud, missing scenes, too few clear controls or read errors.
- **Eligibility** (`engine/app/eligibility.py`): exact location, a closing date, and wording that names a large-area problem. Mumbai: 558 of 77,338 tickets, 291 closed. Bengaluru is never eligible (ward level only). Synthetic tickets run for demonstration but are marked `demo_only` and carry no weight.
- **Evidence:** "unusual change" gives likelihood ratio 0.45 (leans fixed); "no unusual change" gives 1.25 (leans not fixed, weakly). Assumptions are stated in `verifier.assumptions()`; they are not validated against real repairs.
- **Validation** (90 random Mumbai locations with real ticket dates; **23 measured**, 44 cloud-obscured, 23 network read errors): placebo detection 13% (95% CI 3 to 34%) against 10% expected, percentiles consistent with uniform (KS p = 0.40); power 40% at an injected change of 1.5 control spreads, 65% at 2, 95% at 3. The read errors were our load bug (three checks reading six bands each in parallel); fixed afterwards with a global cap of 6 reads, 6 retries with backoff, a window-level retry, and no caching of failures. **The validation was not repeated after the fix.**
- **On real eligible tickets** (the demo-cache run: 71 closed Mumbai tickets with large-area wording, closed mid-April to end of August 2026, live reads with the fixed reader): **46 measured, 25 cloud-obscured, 0 read errors**. Of the 46 measured, **4 (9%) showed unusual change at the site, about the same as the 10 to 13% seen at random places with no repair claimed**; the median site percentile was 0.40, if anything below the controls. So in this sample the closures do not look different from random places. That does not show the work was not done: silt removal and small works are often invisible at 10 m, which is why the evidence is weak. It does mean the satellite check should not be sold as a detector of false closures.
- **Not used:** GEOAI-04's learned U-Net (trained on urban construction change; its README reports weak results in 3 of 10 locations and many farmland false alarms).
- **Runtime:** a live check takes 20 to 40 s (cached: instant). `POST /satellite/check` accepts `cached_only` and `refresh`; `GET /satellite/chip/{ticket_id}/{before|after}.png` serves the image chips. Cache: `data/cache/satellite/` (gitignored); fill it with `python -m app.satellite.precompute`.

### Benchmark v1 (Phase 4, built)
Code: `engine/app/benchmark/make_benchmark.py`. Data: `data/benchmark/benchmark_v1.parquet` (tickets) and `benchmark_v1_truth.parquet` (labels, benchmark use only), both committed. Metrics: `data/models/benchmark_v1.metrics.json`.
- **Base:** 1,000 real closed Mumbai tickets (exact location). **Injected (invented):** 30% marked false closures; symptoms injected with probability: closed in 1 to 9 minutes (40%), photo id reused from an earlier closure (35%), photo GPS 300 to 5,000 m away (30%, a quarter of those only 120 to 300 m so they are ambiguous). Every failure also means "no real work done" (`site_changed = 0`).
- **Results (synthetic injection):** instant closure recall 1.00; photo reuse 1.00; far photo 0.65 (95% CI 0.54 to 0.75); any symptom 0.67 of failures; false alarms on clean tickets 0.7%. **86 of 300 failures (29%) have no symptom** and need independent evidence. Recall on injected symptoms is high by construction; do not quote it as a performance claim.
- **Real finding (not synthetic): batch closing is normal in Mumbai.** 28.9% of the 58,347 real closed tickets share a closing minute with 2 or more others closed by the same officer; the median cluster spans 1.3 km, 17.9% of tickets sit in clusters of 1 km or more, 5.2% of 3 km or more. So same-minute closing is bulk or desk closing and is **not** a signal. It was removed from the benchmark and the detectors. Closing a ticket within 10 minutes of filing is rare (52 of 58,347, 0.09%) and stays as a weak symptom.
- **Pending:** agent cost versus accuracy (needs Ayush's real verifiers) and photo content checks (need the demo photo set).

### All cities at once
`cd engine && python -m app.ingest all` writes one Parquet file per city to `data/warehouse/` in about 35 seconds. Columns differ slightly between cities (each has its own extras); load with DuckDB `union_by_name`.

## Pune
No complaint dataset exists on the PMC open data portal or OpenCity's 40 PMC datasets. The iChangeMyCity archive (Janaagraha, on AWS) is marked deprecated and its bucket denies public listing, so it is **not usable**. PMC Care data is not published.
What we use instead: real PMC ward polygons (58 wards, 2022 map), real stormwater drain (nalla) lines (3,075 segments), plus complaints we generate. Other real Pune layers downloaded for context: SWD chambers, ward-wise streetlight counts. **Every Pune complaint is synthetic.**

## Synthetic cities
Generator: `data/scripts/make_synthetic.py` (seed 7). 5,904 Pune and 5,883 Sandbox tickets; about 21% of closed tickets are false closures **by construction**.
- **Real inputs:** Pune ward polygons and drain lines; resolution-time shapes from Mumbai MARG (pothole median 44.8 h; others median 207 h).
- **Invented:** all tickets, closures, false-closure labels and rates (assumptions: pothole 22%, drain 20%, garbage 18%, water leak 12%, other 12%, streetlight 10%), failure modes, the category mix (borrowed from BBMP/Mumbai), six "bad" officers with 3x the rate, three chronic wards.
- **Failure modes injected:** fast close, batch close at 23:58 by bad officers, reused photo, wrong location (photo more than 300 m away), no work done. Repeat complaints follow within 14 days for 60% of false closures and 8% of true ones.
- **Ground truth:** `gt_false_closure`, `gt_failure_mode`, `gt_site_changed`. These are for the benchmark only. **Never use them as scorer features and never show them in the UI.**
- Sanity check run on Pune: false closures have median 15 h to close vs 142 h for true; 62% blank or "." notes vs 5%; photo ids reused 39% vs 7%.
- **Caveat:** results on these tickets measure how well we detect what we injected, nothing more. Label them "synthetic injection" everywhere.

## What the data tells us about the plan

| Planned | Reality | Decision |
|---|---|---|
| H3 hexagons on all real data | Only Mumbai (and synthetic) have coordinates | Mumbai is the main real dataset for spatial features. Bengaluru uses ward level |
| Time to close, closing hour, batch closing | Bengaluru has no closing time; Mumbai has `AFTER_IMAGE_DATE` | Use these on Mumbai and synthetic only. The proposal's "closing speed and batch patterns" apply there, not to Bengaluru |
| Proxy label: repeat complaint within 14 days after closure | **On Mumbai, 40.3% of 51,769 valid closed tickets have a same-type complaint within about 100 m in the next 14 days, but the placebo (same measurement in the 14 days before filing) is 49.2%.** The plain label mostly measures how crowded a spot is | **Do not use the plain label.** Phase 3 options: label only repeats arriving more than 24 h after closure, normalise against the cell's own base rate, use pothole reopens (27) and `ReOpen` (Bengaluru), or lean on the synthetic ground truth |
| Satellite check | Needs coordinates | Run it on Mumbai tickets (real coordinates) and synthetic tickets, not on Bengaluru |
| Photo check | Mumbai has only image file names; no real photos | Demo photo set for the live demo; the Mumbai "no attended image" flag is a real feature |
| Pune as a real city | No data | Pune is synthetic on real geography, labelled as such |

## Other leads (not downloaded)
- **BBMP work orders and payments 2024-26** (OpenCity): which works were paid, by ward. Could cross-check complaint closures against paid works. Nice extra, not needed for the MVP.
- Pune drains KMZ (22 MB) and more layers on OpenCity's Pune Municipal Corporation page.
- Praja Foundation reports for Mumbai complaint statistics (for Vedashree's citations).
- The Kaggle "Mumbai Nagar Seva BMC complaints" competition dataset is documented as synthetic; do not treat as real.

## Sources
- OpenCity BBMP grievances: https://data.opencity.in/dataset/bbmp-grievances-data
- BMC MARG service: https://marg.mcgm.gov.in/server/rest/services/MARG_APP/MARG_Application_Prod/MapServer
- Pune wards and drains (PMC via OpenCity): https://data.opencity.in/organization/pune-municipal-corporation
- BBMP ward maps (OpenCity): https://data.opencity.in/dataset/bbmp-ward-information
