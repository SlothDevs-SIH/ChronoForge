# Contract

The JSON files in this folder are the data contract between Engine, Agent and the web app. Change a shape here only after telling the other two, and update all three sides.

## Endpoints

**Engine, port 8001**
- `GET /tickets?city=&ward=&category=&status=&min_score=&limit=&offset=`: list of `{ticket, score}`, newest first. Pass `status=closed` to list closed tickets (the ones TrueClose checks)
- `GET /tickets/{id}`, `GET /tickets/{id}/score`
- `GET /cities`: per-city counts plus `data_quality` and `location_precision` for the city switcher and its badge
- `POST /satellite/check` with `{ticket_id, cached_only?, refresh?}`: returns Evidence. Real Sentinel-2 check (20 to 40 s live, instant cached). `details.source` is `live`, `cached` or `not_cached`; abstentions and ineligible tickets are `inconclusive` with `details.reason`. Ineligible costs 0; an attempted check costs 3. `details.demo_only` marks synthetic tickets (no weight). Network failures abstain and are never cached
- `GET /satellite/chip/{ticket_id}/{before|after}.png`: image chips (about 400 m across, site outlined), written by a check. Satellite checks apply to large-area problems only (dump sites, nullah corridors, waterlogging, large encroachment). Potholes and single garbage piles are below the 10 m pixel: `Score.satellite_eligible` is false, `Score.satellite_reason` starts with "not applicable", and the check returns inconclusive at cost 0. Show `satellite_reason` instead of offering the check.
- `GET /wards/stats?city=&category=&limit=`: per ward and category, `official_rate` (share no longer open), `reopen_rate`, counts, and `honest_rate`
- `GET /eval/results`, `POST /connectors/{mumbai|bengaluru|pune|synthetic}/sync`, `GET /health` (shows `mode`: `warehouse` or `fixtures`)

**Reading a score.** `p_false_closure` is the agent's prior. `score.score_type` says what it is, and the UI must show it accordingly:
- `calibrated_probability`: synthetic cities only (ground truth by construction; clipped to 0.02 to 0.98).
- `risk_rank_prior`: Bengaluru. A rank mapped into 0.30 to 0.70; `risk_percentile` says where the ticket ranks. NOT a probability.
- `rule_flags`: Mumbai. 0.5, or about 0.68 when `flags` contains `citizen_image_only`. NOT a probability.
- `baseline`: no model applies (open tickets, older Bengaluru tickets). The neutral 0.5.
`reasons` (per-ticket TreeSHAP, or the flag) are only filled by `GET /tickets/{id}/score`, not in lists. `GET /tickets?sort=risk` ranks by `p_false_closure`.

`GET /eval/results` now returns `{scorers: {model_name: metrics}, verifiers: [...], verifiers_are_placeholder: true}`. Scorer metrics are real; verifier values stay placeholders until Phase 4. `verifiers` now holds `{satellite: ..., benchmark_v1: ...}` (real metrics with caveats; the benchmark is synthetic injection); `pending` lists what is not measured yet. Still true: `honest_rate` in `/wards/stats` is `null`.
- Simulated municipal system: `GET /muni/tickets`, `POST /muni/tickets/{id}/reopen`, `POST /muni/tickets/{id}/escalate`

**Agent, port 8002**
- `POST /agent/run/{ticket_id}` returns `{run_id}` at once; the run is a background thread. A ticket the Engine cannot score ends the run with `status: "error"` (no invented prior)
- `GET /agent/stream/{run_id}`: SSE. Events are **named**: `event: trace` with a trace-event JSON, then `event: end` with `{status}`. Clients must listen for `trace` (an unnamed `onmessage` never fires)
- `GET /agent/runs/{run_id}` returns `{run_id, ticket_id, status, trace: [...], verdict}`
- `POST /evidence/photo`; citizen: `POST /citizen/{ticket_id}/contact` (register a demo chat), `POST /citizen/{ticket_id}/ask`, `POST /citizen/send`; channels: `POST /telegram/webhook`, `GET|POST /whatsapp/webhook` (also under `/channels/...`)
- `GET /approvals?status=` (default `pending`), `POST /approvals/{id}/decide` with `{decision: approve|reject, note}`; approving calls the Engine's `/muni/tickets/{id}/reopen` or `/escalate`
- `GET /outcomes`, `GET /audit`, `GET /audit/verify`

The web app reaches both through the Vite proxy: `/api/engine/*` and `/api/agent/*`.

## The `demo` city
12 synthetic tickets (`DEMO-000` to `DEMO-g00`) built from `demo/photos/manifest.json`: real open-licence photo content with synthetic EXIF, four kinds of planted failure (reused photo, shifted GPS, stale timestamp, still broken). `closure_photo_url` and `complaint_photo_url` are repo-relative paths the Agent resolves. The planted failures are ground truth in `truth_demo.parquet`, never on the ticket. See `INTEGRATION.md`.

## Ticket location fields
`lat`, `lng` and `h3` can be null. `location_precision` says how much to trust them: `exact` (Mumbai), `generated` (synthetic cities), `ward_centroid` (Bengaluru, a ward's centre, h3 is null), `none`. Satellite checks and 100 m repeat features may only use `exact` and `generated`.

## Fusion rule (Agent and Engine must agree)
Each Evidence has `likelihood_ratio = P(evidence | not fixed) / P(evidence | fixed)`. Above 1 means "not fixed", below 1 means "fixed", 1 means inconclusive.
`logit(posterior) = logit(prior) + sum(ln(LR))`. Verdict: `likely_not_fixed` if posterior >= 0.75, `verified_fixed` if <= 0.25, else `cannot_tell`. The score alone never gives a verdict: at least one independent check runs first. Thresholds live in `agent/app/config.py`.

## Rounds
Kickoff 10:00, checkpoint 16:00, checkpoint 22:00, final tomorrow 10:00 (confirm the exact round format with the organisers).

## Ground rules
1. Anything on a slide or in the pitch must be something we can show live or point to in the repo.
2. Simulated parts are labelled in the UI: the municipal endpoint, cached satellite results, demo photos, synthetic data.
3. GEOAI-04 and the Catalyst AI engines are earlier projects that we reuse and acknowledge. The closure-integrity logic, agent, connectors and verification loop are new this weekend.
4. No reopen, escalate or penalty without an approval record.
5. No secrets in git. Use `.env`; commit only `.env.example`.
6. SQL schemas and migrations are written as `.sql` files and reviewed by a person before running on a shared database.
