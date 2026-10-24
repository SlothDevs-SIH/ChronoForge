-- Agent service schema (SQLite). Review before applying to any shared database.
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
  decided_at TEXT
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
CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  pw_hash TEXT NOT NULL,         -- scrypt, see app/auth.py
  role TEXT NOT NULL,            -- citizen | officer | admin (server-side only, never taken from the client after sign-up)
  status TEXT NOT NULL,          -- active | pending (officer awaiting admin approval) | disabled
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_tickets (
  user_id TEXT NOT NULL,
  ticket_id TEXT NOT NULL,
  added_at TEXT NOT NULL,
  PRIMARY KEY (user_id, ticket_id)
);
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
