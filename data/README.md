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
