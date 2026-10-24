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
  status TEXT NOT NULL,          -- registered | asked | answered | opted_out
  created_at TEXT NOT NULL,
  asked_at TEXT,
  answered_at TEXT
);
