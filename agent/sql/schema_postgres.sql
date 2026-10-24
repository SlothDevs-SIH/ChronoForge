-- TrueClose Agent service: Postgres schema for Supabase.
--
-- HOW TO USE: open the Supabase dashboard, SQL Editor, paste this whole file and run it ONCE on a new project.
-- The application never creates or alters tables in Postgres mode; it only reads and writes rows.
-- It is safe to re-run (every statement is IF NOT EXISTS), but it does not migrate old data.
--
-- Row Level Security is switched on for every table with NO policies. The Agent connects with the database
-- connection string (the postgres role bypasses RLS), while the public Supabase API (anon key) can read nothing here.

CREATE TABLE IF NOT EXISTS evidence (
  evidence_id TEXT PRIMARY KEY,
  ticket_id TEXT NOT NULL,
  run_id TEXT,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS evidence_ticket ON evidence (ticket_id, created_at);

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  ticket_id TEXT NOT NULL,
  status TEXT NOT NULL,                 -- running | done | error
  verdict TEXT,                         -- Verdict JSON
  trace TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
  approval_id TEXT PRIMARY KEY,
  ticket_id TEXT NOT NULL,
  run_id TEXT,
  action TEXT NOT NULL,
  verdict_snapshot TEXT NOT NULL,
  status TEXT NOT NULL,                 -- pending | approved | rejected
  note TEXT,
  engine_result TEXT,
  created_at TEXT NOT NULL,
  decided_at TEXT,
  actor TEXT,                           -- user id of the person who decided
  actor_email TEXT
);
CREATE INDEX IF NOT EXISTS approvals_status ON approvals (status, created_at);

CREATE TABLE IF NOT EXISTS outcomes (
  outcome_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  approval_id TEXT NOT NULL,
  ticket_id TEXT NOT NULL,
  predicted TEXT NOT NULL,
  observed TEXT,
  created_at TEXT NOT NULL
);

-- Append-only, hash-chained audit log (the application only ever inserts into it).
CREATE TABLE IF NOT EXISTS audit (
  idx BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ts TEXT NOT NULL,
  event TEXT NOT NULL,                  -- canonical JSON
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS citizen_requests (
  ticket_id TEXT PRIMARY KEY,
  chat_id TEXT NOT NULL,                -- needed to send; only chat_hash is ever logged or shown to an LLM
  chat_hash TEXT NOT NULL,
  lang TEXT NOT NULL DEFAULT 'en',
  channel TEXT NOT NULL DEFAULT 'telegram',   -- telegram | whatsapp
  status TEXT NOT NULL,                 -- registered | asked | answered | superseded | opted_out
  created_at TEXT NOT NULL,
  asked_at TEXT,
  answered_at TEXT
);
CREATE INDEX IF NOT EXISTS citizen_requests_chat ON citizen_requests (chat_id, channel, status);

CREATE TABLE IF NOT EXISTS kv (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL
);

-- ---- sign-in, roles and linked tickets --------------------------------------------------------------------
-- Roles live here, never in client-editable metadata. Only status = 'active' grants anything.
CREATE TABLE IF NOT EXISTS app_users (
  user_id TEXT PRIMARY KEY,             -- the Supabase user id (JWT sub)
  email TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'citizen' CHECK (role IN ('citizen', 'officer', 'admin')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'pending', 'rejected')),
  requested_role TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  decided_by TEXT,
  decided_at TEXT
);
CREATE INDEX IF NOT EXISTS app_users_status ON app_users (status, role);

CREATE TABLE IF NOT EXISTS user_tickets (
  user_id TEXT NOT NULL,
  ticket_id TEXT NOT NULL,
  linked_by TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, ticket_id)
);

-- ---- persisted verification runs --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS verification_runs (
  run_id TEXT PRIMARY KEY,
  ticket_id TEXT NOT NULL,
  status TEXT NOT NULL,                 -- done | pending (could not run; the reason is in the record)
  record TEXT NOT NULL,                 -- JSON, see contract/AUTH_AND_DEPLOY.md
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS verification_runs_ticket ON verification_runs (ticket_id, created_at);

-- ---- citizen evidence photos and reply links --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence_uploads (
  evidence_id TEXT PRIMARY KEY,
  ticket_id TEXT NOT NULL,
  user_id TEXT,
  sha256 TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  storage_key TEXT NOT NULL,
  exif_summary TEXT,                    -- server-side only: original EXIF position/time and the location check; never returned
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

-- ---- website requests: case history, reliable citizen messages, citizen photos ------------------------------
CREATE TABLE IF NOT EXISTS case_events (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ticket_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  kind TEXT NOT NULL,
  text TEXT NOT NULL,
  audience TEXT NOT NULL DEFAULT 'citizen'
);
CREATE INDEX IF NOT EXISTS case_events_ticket ON case_events (ticket_id, id);
CREATE TABLE IF NOT EXISTS outbox (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ticket_id TEXT,
  channel TEXT NOT NULL,
  chat_id TEXT NOT NULL,
  text TEXT NOT NULL,
  buttons TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_try DOUBLE PRECISION NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
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

-- ---- lock the public API out of every table ---------------------------------------------------------------
ALTER TABLE evidence          ENABLE ROW LEVEL SECURITY;
ALTER TABLE runs              ENABLE ROW LEVEL SECURITY;
ALTER TABLE approvals         ENABLE ROW LEVEL SECURITY;
ALTER TABLE outcomes          ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit             ENABLE ROW LEVEL SECURITY;
ALTER TABLE citizen_requests  ENABLE ROW LEVEL SECURITY;
ALTER TABLE kv                ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_users         ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_tickets      ENABLE ROW LEVEL SECURITY;
ALTER TABLE verification_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_uploads  ENABLE ROW LEVEL SECURITY;
ALTER TABLE reply_links       ENABLE ROW LEVEL SECURITY;
ALTER TABLE idempotency_keys  ENABLE ROW LEVEL SECURITY;
ALTER TABLE case_events       ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbox            ENABLE ROW LEVEL SECURITY;
ALTER TABLE case_photos       ENABLE ROW LEVEL SECURITY;
