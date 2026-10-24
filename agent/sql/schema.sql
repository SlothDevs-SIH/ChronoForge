-- Agent service schema (SQLite: local runs and tests). Postgres uses agent/sql/schema_postgres.sql, run by a person.
CREATE TABLE IF NOT EXISTS evidence (
  evidence_id TEXT PRIMARY KEY,
  ticket_id TEXT NOT NULL,
  run_id TEXT,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  ticket_id TEXT NOT NULL,
  status TEXT NOT NULL,          -- running | done | error
  verdict TEXT,                  -- Verdict JSON
  trace TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
  approval_id TEXT PRIMARY KEY,
  ticket_id TEXT NOT NULL,
  run_id TEXT,
  action TEXT NOT NULL,
  verdict_snapshot TEXT NOT NULL,
  status TEXT NOT NULL,          -- pending | approved | rejected
  note TEXT,
  engine_result TEXT,
  created_at TEXT NOT NULL,
  decided_at TEXT,
  actor TEXT,                    -- user id of the person who decided
  actor_email TEXT
);
CREATE TABLE IF NOT EXISTS outcomes (
  outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
  approval_id TEXT NOT NULL,
  ticket_id TEXT NOT NULL,
  predicted TEXT NOT NULL,
  observed TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
  idx INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  event TEXT NOT NULL,           -- canonical JSON
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS citizen_requests (
  ticket_id TEXT PRIMARY KEY,
  chat_id TEXT NOT NULL,         -- needed to send; only chat_hash is ever logged or shown to an LLM
  chat_hash TEXT NOT NULL,
  lang TEXT NOT NULL DEFAULT 'en',
  channel TEXT NOT NULL DEFAULT 'telegram',   -- telegram | whatsapp
  status TEXT NOT NULL,          -- registered | asked | answered | superseded | opted_out
  created_at TEXT NOT NULL,
  asked_at TEXT,
  answered_at TEXT
);
CREATE TABLE IF NOT EXISTS kv (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL
);

-- ---- sign-in, roles and linked tickets ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_users (
  user_id TEXT PRIMARY KEY,      -- the sign-in provider's user id (JWT sub)
  email TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'citizen',        -- citizen | officer | admin
  status TEXT NOT NULL DEFAULT 'active',       -- active | pending | rejected
  requested_role TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  decided_by TEXT,
  decided_at TEXT
);
CREATE TABLE IF NOT EXISTS user_tickets (
  user_id TEXT NOT NULL,
  ticket_id TEXT NOT NULL,
  linked_by TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, ticket_id)
);
-- ---- persisted verification runs ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS verification_runs (
  run_id TEXT PRIMARY KEY,
  ticket_id TEXT NOT NULL,
  status TEXT NOT NULL,          -- done | pending (could not run, reason in the record)
  record TEXT NOT NULL,          -- JSON, see contract/AUTH_AND_DEPLOY.md
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS verification_runs_ticket ON verification_runs (ticket_id, created_at);
-- ---- citizen evidence photos and reply links ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence_uploads (
  evidence_id TEXT PRIMARY KEY,
  ticket_id TEXT NOT NULL,
  user_id TEXT,
  sha256 TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  storage_key TEXT NOT NULL,
  exif_summary TEXT,             -- server-side only: original EXIF position/time and the location check; never returned
  created_at TEXT NOT NULL,
  UNIQUE (ticket_id, sha256)
);
CREATE TABLE IF NOT EXISTS reply_links (
  token_id TEXT PRIMARY KEY,
  ticket_id TEXT NOT NULL,
  lang TEXT NOT NULL DEFAULT 'en',
  expires_at TEXT NOT NULL,
  used_at TEXT,
  created_by TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS idempotency_keys (
  user_id TEXT NOT NULL,
  idem_key TEXT NOT NULL,
  ticket_id TEXT NOT NULL,
  response TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, idem_key)
);

-- ---- website requests: case history, reliable citizen messages, citizen photos ------------------------------------
CREATE TABLE IF NOT EXISTS case_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  kind TEXT NOT NULL,
  text TEXT NOT NULL,
  audience TEXT NOT NULL DEFAULT 'citizen'   -- citizen: the citizen and staff can see it; staff: staff only
);
CREATE INDEX IF NOT EXISTS case_events_ticket ON case_events (ticket_id, id);
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id TEXT,
  channel TEXT NOT NULL,
  chat_id TEXT NOT NULL,
  text TEXT NOT NULL,
  buttons TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_try REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',    -- pending | sent | failed
  last_error TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS case_photos (
  photo_id TEXT PRIMARY KEY,
  ticket_id TEXT NOT NULL,
  chat_hash TEXT NOT NULL,
  phash TEXT NOT NULL,
  path TEXT NOT NULL,
  details TEXT NOT NULL,
  created_at TEXT NOT NULL
);
