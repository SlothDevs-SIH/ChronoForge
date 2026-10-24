# Contract

The JSON files in this folder are the data contract between Engine, Agent and the web app. Change a shape here only after telling the other two, and update all three sides.

## Endpoints

**Engine, port 8001**
- `GET /tickets?city=&ward=&category=&status=&min_score=&limit=&offset=`: list of `{ticket, score}`, newest first. Pass `status=closed` to list closed tickets (the ones TrueClose checks)
- `GET /tickets/{id}`, `GET /tickets/{id}/score`
- `GET /cities`: per-city counts plus `data_quality` and `location_precision` for the city switcher and its badge
- `POST /satellite/check` with `{ticket_id}`: returns Evidence
- `GET /wards/stats?city=&category=&limit=`: per ward and category, `official_rate` (share no longer open), `reopen_rate`, counts, and `honest_rate`
- `GET /eval/results`, `POST /connectors/{mumbai|bengaluru|pune|synthetic}/sync`, `GET /health` (shows `mode`: `warehouse` or `fixtures`)

Until the Phase 3 scorer exists: every real ticket's score is the neutral baseline (`p_false_closure` 0.5, `model_version` "baseline-no-model", no reasons), `honest_rate` is `null`, and `/satellite/check` returns "inconclusive" with `details.stub=true` for eligible tickets and cost 0 for ineligible ones. The UI should show these honestly, not as results.
- Simulated municipal system: `GET /muni/tickets`, `POST /muni/tickets/{id}/reopen`, `POST /muni/tickets/{id}/escalate`

**Agent, port 8002**
- `POST /agent/run/{ticket_id}` returns `{run_id}`; `GET /agent/stream/{run_id}` (SSE trace); `GET /agent/runs/{run_id}`
- `POST /evidence/photo`, `POST /citizen/send`, `POST /telegram/webhook`, `GET /whatsapp/webhook`
- `GET /approvals?status=`, `POST /approvals/{id}/decide` with `{decision: approve|reject, note}`
- `GET /audit`, `GET /audit/verify`

The web app reaches both through the Vite proxy: `/api/engine/*` and `/api/agent/*`.

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
