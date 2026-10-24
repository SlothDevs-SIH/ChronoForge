# TrueClose: shared contract and master timeline

Read this first, all four of you. It is the only file that binds the other four together.
Team Slothdevs: Soham, Ayush, Ishan, Vedashree. Track: Agentic AI. Theme: Cities of the Future.

## 1. What we are building (one paragraph)

TrueClose is an agent that sits on top of a municipal complaint system. For every ticket marked "resolved" it produces a calibrated probability that the closure is false. For doubtful tickets it picks the cheapest independent check (photo forensics, satellite change, citizen confirmation, human spot check), fuses the evidence, and either confirms the closure, flags it for reopen/escalation (a human approves), or says "can't tell". Afterwards it re-scores itself against the outcome. Closing a ticket stops being the end of the story.

## 1b. Decisions locked (24 Oct)

Multi-city data (Bengaluru, Pune, Mumbai, synthetic); demo photos from a labelled demo set; label strategy D; broad scope; DuckDB + Parquet (Q3 A); scorer = LightGBM + logistic ensemble; satellite via live AWS Earth Search STAC with cache fallback (Q6 A); FastAPI (Q7 A); photo check = imagehash + EXIF + CLIP (DINOv2-small stretch); LLM-chosen tools with Gemini (AI Studio) then OpenAI then deterministic fallback; Telegram first then WhatsApp Cloud; keyword-then-LLM replies; React + Vite + TS, MapLibre + deck.gl; demo on a laptop and deployed. Full detail: `PROJECT_OVERVIEW.md`. Open: colour palette, Research/PPT questions (Q17, Q19).

Contract addition: the Engine's list endpoints accept `?city=bengaluru|pune|mumbai|synthetic`, and every Ticket carries `"city"` and `"data_quality": "real | partial | synthetic"`.

## 2. Who owns what

| Person | File | Owns |
|---|---|---|
| Soham | `backend_soham.md` | **Engine service** (port 8001): data ingest, municipal connectors, H3 index, closure-integrity scorer, satellite verifier, evaluation benchmark, ward stats |
| Ayush | `backend_ayush.md` | **Agent service** (port 8002): evidence (photo) verifier, agent planner and fusion, citizen channel (Telegram/WhatsApp), approvals, audit log |
| Ishan | `frontend_ishan.md` | Everything a judge sees: dashboard, triage queue, ticket detail, agent trace, citizen page, eval page |
| Vedashree | `research_vedashri.md` | Deck for each round, claims register, pitch script, judge Q&A, field research with real citizens, demo script |
| Everyone | `questions.md` | Decisions that need an answer before we lock the stack |

## 3. Data contracts (JSON, snake_case, ISO-8601 UTC timestamps)

These are frozen after hour 1. Changes need a message in the group chat and a version bump here.

### Ticket
```json
{
  "ticket_id": "bbmp-2024-0001234",
  "source": "bbmp_csv | mock_muni | citizen_telegram",
  "category": "pothole | garbage | streetlight | drain | water_leak | other",
  "text": "string",
  "lang": "en | hi | mr | kn | other",
  "lat": 12.97, "lng": 77.59,
  "h3": "89618924c6bffff",
  "ward": "string",
  "created_at": "...", "closed_at": "...",
  "closed_by_hash": "sha1 of officer id or null",
  "status": "open | closed | reopened",
  "closure_note": "string or null",
  "closure_photo_url": "string or null"
}
```

### Score (Engine returns)
```json
{
  "ticket_id": "...",
  "p_false_closure": 0.71,
  "model_version": "lgbm-v1",
  "reasons": [{"feature": "repeat_14d_same_cell", "value": 3, "shap": 0.42}],
  "eligible_checks": ["photo", "satellite", "citizen", "human"],
  "satellite_eligible": true
}
```

### Evidence (either service returns, Agent service stores)
```json
{
  "evidence_id": "uuid",
  "ticket_id": "...",
  "check": "photo | satellite | citizen | human",
  "verdict": "supports_fix | contradicts_fix | inconclusive",
  "likelihood_ratio": 0.2,
  "confidence": 0.8,
  "cost": 1,
  "details": {},
  "created_at": "..."
}
```
`likelihood_ratio` is P(evidence | not fixed) / P(evidence | fixed). Below 1 means the evidence says it was fixed, above 1 means it was not. Inconclusive means 1.0.

### Verdict (Agent returns)
```json
{
  "ticket_id": "...",
  "state": "verified_fixed | likely_not_fixed | cannot_tell",
  "prior": 0.71, "posterior": 0.88,
  "evidence_ids": ["..."],
  "recommended_action": "none | ask_citizen | reopen | escalate | human_spot_check",
  "requires_human": true,
  "explanation": "plain-language string"
}
```
Fusion rule (both sides must agree): `logit(posterior) = logit(prior) + sum(ln(LR_i))`. `likely_not_fixed` if posterior >= 0.75, `verified_fixed` if <= 0.25, otherwise `cannot_tell`. Thresholds live in one config file in the Agent service.

### Agent trace event (streamed to frontend over SSE)
```json
{"run_id":"...","step":3,"type":"thought | tool_call | tool_result | verdict | approval_needed","tool":"check_satellite","summary":"string","cost_spent":4,"budget_left":6,"ts":"..."}
```

## 4. Endpoints

**Engine (Soham), `http://localhost:8001`**
- `GET /tickets?ward=&category=&status=&min_score=&limit=` returns a list of Ticket plus the latest score
- `GET /tickets/{id}` returns Ticket
- `GET /tickets/{id}/score` returns Score
- `POST /satellite/check` takes `{ticket_id}` and returns Evidence (with before/after tile URLs in `details`)
- `GET /wards/stats` returns official resolution rate vs honest rate, per ward and category
- `GET /eval/results` returns benchmark metrics, calibration curve points, ablations
- `POST /connectors/{name}/sync` pulls from a connector
- Mock municipal system: `POST /muni/tickets/{id}/reopen`, `POST /muni/tickets/{id}/escalate`, `GET /muni/tickets` (clearly labelled as a simulated municipal endpoint)

**Agent (Ayush), `http://localhost:8002`**
- `POST /evidence/photo` takes `{ticket_id, closure_photo_url, citizen_photo_url?}` and returns Evidence
- `POST /agent/run/{ticket_id}` returns `{run_id}`
- `GET /agent/stream/{run_id}` is SSE of trace events
- `GET /agent/runs/{run_id}` returns the full trace plus Verdict
- `POST /citizen/send` takes `{ticket_id, channel}`
- `POST /telegram/webhook`, `GET/POST /whatsapp/webhook`
- `GET /approvals` returns the pending queue; `POST /approvals/{id}/decide` takes `{decision, note}` and, if approved, calls the Engine's `/muni/.../reopen`
- `GET /audit` returns the hash-chained log

**Frontend** talks to both through the Vite dev proxy: `/api/engine/*` goes to 8001, `/api/agent/*` goes to 8002.

## 5. Repo layout (monorepo, one GitHub repo)

```
trueclose/
  engine/        # Soham   (FastAPI)
  agent/         # Ayush   (FastAPI)
  web/           # Ishan   (React + Vite)
  data/          # sample CSVs, benchmark, cached satellite tiles (git-lfs or small subset only)
  docs/          # Vedashree: deck, claims register, screenshots
  contract/      # the JSON examples above as real files, used as test fixtures
  docker-compose.yml
```
Branches: `main` is always demoable. Everyone works on `feat/<name>-<thing>` and merges by squash. Nobody pushes to `main` after 22:00 without a second person watching.

## 6. Master timeline

Assumption (confirm in `questions.md` Q0): kickoff 10:00, Round A at 16:00, Round B at 22:00, final submission and judging at 10:00 tomorrow.

| Time | Goal | Gate |
|---|---|---|
| 10:00-11:00 | **Hour zero.** Repo, contract frozen, Soham downloads a BBMP grievance file and reports the real columns, Ayush creates the bot tokens, Ishan scaffolds with fixtures, Vedashree opens the claims register | Real column list posted in chat |
| 11:00-13:00 | Walking skeleton: one ticket flows ingest, score, agent run, verdict, shown on screen (stubs allowed) | Ishan's screen shows a ticket from a live API |
| 13:00-16:00 | First real versions: scorer v1, photo verifier v1, agent loop with fake satellite, ward map | **Round A at 16:00.** Show the skeleton plus 1 real number |
| 16:00-19:00 | Real satellite check, real Telegram round-trip, mock municipal reopen, approvals | One end-to-end ticket with all four check types |
| 19:00-22:00 | Evaluation benchmark and numbers, polish, bug bash | **Round B at 22:00.** Full demo plus eval page |
| 22:00-02:00 | Fix what Round B exposed, deploy, record backup demo video | Deployed URL works from a phone |
| 02:00-07:00 | **Sleep in shifts.** At least two people sleep 4 hours, swapped. A tired demo is the biggest hidden risk | |
| 07:00-09:00 | Freeze. Only bug fixes. Rehearse the pitch twice | Code freeze at 08:30 |
| 09:00-10:00 | Final checks: deck, repo README, video, links | Submit |

## 7. Ground rules

1. **Claims discipline.** Anything on a slide or in the pitch must be something we can show live or point to in the repo by 10:00 tomorrow. The proposal lists WhatsApp, satellite and municipal connectors as MVP, so we build real thin versions of all three. Where something is simulated (the municipal endpoint, tiles pre-cached for speed), the UI says so. Judges can click through, and one caught overclaim costs more than any missing feature.
2. **Prior work.** We reuse code from GEOAI-04 and the Catalyst AI engines. It may be copied into this repo, but it is **acknowledged** in the README and slides as prior components ("built earlier; the closure-integrity logic, agent, connectors and verification loop are new this weekend"). The hackathon rules bar submitting earlier work as new, and the repo history will show copied files arriving, so the honest line protects us. Keep copied code in its own folder with a NOTICE.md. Do not paste whole files from Aegis-AI or DHRUVA.
3. **Human in the loop.** No code path reopens, escalates or penalises anything without an approval record.
4. **No secrets in git.** `.env` only, `.env.example` committed.
5. **Fixtures first.** Ayush and Soham publish contract-shaped fixture JSON in the first hour so Ishan is never blocked.
6. **Database changes.** Any SQL schema or migration is written as a `.sql` file in `engine/sql/` and reviewed by a human before it is run against a shared database.
