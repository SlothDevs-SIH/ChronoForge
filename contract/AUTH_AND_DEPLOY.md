# Auth, roles and deploy contract (shared by Engine, Agent and web)

Decisions (from the project owner, 24 Oct): host Engine and Agent on **Render**; **Supabase Auth** for sign-in; Postgres for the **Agent only** (the Engine keeps DuckDB over Parquet, about 28 MB for roughly 822,800 tickets); the web app uses **plain CSS** (no Tailwind) for auth pages; **no social login** for now; the **citizen role only sees the tickets linked to them** and cannot create tickets; **officers are admin-approved**; the first admins are the four team members, listed in `ADMIN_EMAILS`; keep the current green palette. No likelihood ratio, prior, threshold or verdict rule may change.

## Environment variables (all services read them; nothing is hardcoded)

| Variable | Used by | Meaning |
|---|---|---|
| `AUTH_REQUIRED` | Engine, Agent | `1` in production. `0` (default) keeps the local demo open: every request is treated as an anonymous admin-equivalent *only for local runs* |
| `SUPABASE_URL` | Engine, Agent | e.g. `https://xxxx.supabase.co`. JWKS is read from `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` |
| `SUPABASE_JWT_SECRET` | Engine, Agent | optional; if set, tokens are verified as HS256 with it (legacy Supabase projects and the test suites). Otherwise asymmetric keys from JWKS |
| `SUPABASE_JWT_AUDIENCE` | Engine, Agent | default `authenticated` |
| `ADMIN_EMAILS` | Agent | comma-separated. A user with a confirmed email in this list becomes `admin` on first profile creation |
| `AGENT_URL` | Engine | base URL of the Agent, used to look up a caller's role (`GET /auth/me`) |
| `ENGINE_URL` | Agent | already exists |
| `ENGINE_SERVICE_TOKEN` | Engine, Agent | shared secret the Agent sends as `X-Service-Token` on `/muni/*` calls and the Engine requires there |
| `CORS_ORIGINS` | Engine, Agent | comma-separated allowlist, e.g. `https://trueclose-neon.vercel.app,http://localhost:5174` |
| `PUBLIC_DEMO_RUNS` | Agent | `1` lets anonymous callers start and stream runs for `DEMO-*` tickets only (so the public Platform page works) |
| `REPLY_LINK_SECRET` | Agent | HMAC key for citizen reply links |
| `DATABASE_URL` | Agent | Postgres URL. Unset = SQLite file `AGENT_DB` (local and tests) |
| `UPLOAD_DIR` / `STORAGE_BACKEND` / `SUPABASE_SERVICE_KEY` / `SUPABASE_BUCKET` | Agent | evidence photo storage: `local` (default) or `supabase` (private bucket, short-lived signed URLs) |
| `WAREHOUSE_DIR` / `WAREHOUSE_URL` | Engine | where the Parquet files live; if missing at start and `WAREHOUSE_URL` is set, a `.tar.gz` is downloaded and unpacked there |

## Identity and roles

- The browser signs in with Supabase and sends `Authorization: Bearer <access_token>` to both services. Both verify the JWT (signature, expiry, audience). A bad or missing token is `401`.
- Roles live in the **Agent's database** (`app_users`), never in client-editable metadata. The Engine asks the Agent `GET /auth/me` (forwarding the same bearer token) and caches the answer for 60 seconds.
- `role` is one of `citizen`, `officer`, `admin`. `status` is one of `active`, `pending`, `rejected`. Only `status = active` grants anything. `pending` and `rejected` users can call `GET /auth/me` and nothing else.
- Citizens can sign up themselves (`role=citizen, status=active`) and see **only tickets an admin has linked to them**. Officer sign-up creates `role=officer, status=pending` until an admin approves. Admins are created from `ADMIN_EMAILS` (the email must be confirmed in the token: `email_verified` or a Supabase-confirmed `email`).

### Permission matrix (enforced per endpoint, covered by tests)

| Endpoint | anonymous | citizen (linked tickets only) | officer | admin |
|---|---|---|---|---|
| `GET /health`, `GET /ready` (both services) | yes | yes | yes | yes |
| Engine `GET /cities`, `GET /eval/results`, `GET /media/demo/...` | yes | yes | yes | yes |
| Engine `GET /tickets` (list), `GET /wards/stats`, `GET /wards/map` | no | no | yes | yes |
| Engine `GET /tickets/{id}`, `/tickets/{id}/score`, `/satellite/chip/...`, `POST /satellite/check` | no | own linked ticket only (satellite check: no) | yes | yes |
| Engine `POST /connectors/{name}/sync` | no | no | no | yes (plus existing admin token) |
| Engine `/muni/*` | only with `X-Service-Token` | no | no | no |
| Agent `GET /auth/me`, `POST /auth/profile` | needs a token | yes | yes | yes |
| Agent `POST /agent/run/{ticket}` and `GET /agent/stream/{run}`, `GET /agent/runs/{run}` | `DEMO-*` tickets only when `PUBLIC_DEMO_RUNS=1` | no | yes | yes |
| Agent `GET /approvals`, `POST /approvals/{id}/decide` | no | no | yes (decide records actor and note) | yes |
| Agent `GET /audit`, `/audit/verify`, `/outcomes` | no | no | yes | yes |
| Agent `GET /verification/{ticket}` and `/latest` | no | own linked ticket only | yes | yes |
| Agent `GET /me/tickets` | no | yes | yes (empty list) | yes (empty list) |
| Agent `GET /admin/users`, `POST /admin/users/{id}/approve|reject|role`, `POST|DELETE /admin/users/{id}/tickets` | no | no | no | yes |
| Agent `POST /citizen/reply-links` | no | no | yes | yes |
| Agent `GET /reply/{token}`, `POST /reply/{token}` | yes (signed link, rate limited) | yes | yes | yes |
| Agent `POST /tickets/{id}/evidence/photo`, `GET /evidence/{id}/url` | no | own linked ticket only | yes | yes |
| Agent `POST /citizen/{id}/contact`, `/citizen/send`, `/citizen/{id}/ask`, `/evidence/photo` | existing admin token **or** officer/admin role | no | yes | yes |
| Agent Telegram and WhatsApp webhooks | unchanged (their own secrets) | | | |

Approving never happens automatically: `decide` is the only path to a reopen, and it records `actor` (user id), `actor_email`, timestamp and the note in the approvals row and in the hash-chained audit.

## New and changed response shapes

`GET /auth/me` returns `{ "user_id": str, "email": str, "role": "citizen"|"officer"|"admin", "status": "active"|"pending"|"rejected", "requested_role": str|null, "ticket_ids": [str] }`. It creates the profile on first call. `POST /auth/profile` body `{ "requested_role": "citizen"|"officer" }` sets the officer request (only allowed while the user has no active privileged role).

`GET /verification/{ticket_id}/latest` returns the persisted run record:
```json
{
  "run_id": "...", "ticket_id": "...", "created_at": "...",
  "config_version": "v1", "calibrated": false,
  "closure_claimed": "closed",
  "verification_verdict": "verified_fixed|likely_not_fixed|cannot_tell|not_performed",
  "review_state": "none|pending|approved|rejected",
  "prior": 0.5, "posterior": 0.5,
  "checks": [ { "check": "photo|satellite|citizen|human", "performed": true, "skipped_reason": null,
                "verdict": "supports_fix|contradicts_fix|inconclusive", "likelihood_ratio": 1.0, "cost": 1 } ],
  "provenance": { "data_quality": "real|partial|synthetic", "score_type": "baseline|risk_rank_prior|rule_flags|calibrated_probability", "city": "..." },
  "note": "Likelihood ratios are configured priors, not measured on real closures."
}
```
`verification_verdict` is `not_performed` only when **every** check was skipped or none ran. An unavailable satellite result is `performed: false` with a `skipped_reason`, never evidence.

Every non-2xx response from both services is `{ "error": { "code": str, "message": str }, "request_id": str }` with the matching HTTP status. Every response carries `X-Request-ID`.

Citizen reply link: `POST /citizen/reply-links` body `{ "ticket_id": str, "lang": "en|hi|mr|kn", "ttl_hours": 336 }` returns `{ "token": str, "expires_at": str }`. `GET /reply/{token}` returns `{ "ticket_id", "category", "ward", "lang", "status": "open|answered|expired" }`. `POST /reply/{token}` body `{ "answer": "yes|partly|no", "lang": str }` stores the answer through the existing citizen-reply evidence path (same likelihood ratios), writes an audit entry and marks the link used.

Evidence photo upload: `POST /tickets/{ticket_id}/evidence/photo`, multipart field `file`, header `Idempotency-Key`. JPEG, PNG and WebP only, checked by magic bytes, at most 8 MB, content hash stored, stored copy has EXIF (including GPS) stripped, **no likelihood ratio is applied** (stored for human review). Returns `{ "evidence_id", "sha256", "duplicate": bool }`.

## Database

The Agent uses SQLite by default (local and tests) and Postgres when `DATABASE_URL` is set. In Postgres mode the application **does not create tables**: the SQL in `agent/sql/schema_postgres.sql` is run by a person in the Supabase SQL editor. Existing tables keep their meaning; new tables: `app_users`, `user_tickets`, `verification_runs`, `evidence_uploads`, `reply_links`, `idempotency_keys`.
