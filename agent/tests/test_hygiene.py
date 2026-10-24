"""Error shape, request ids, logs, readiness, CORS, and the database adapter (including Postgres mode against a fake driver)."""
import json
import logging
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import approvals, config, db, http_utils
from app.main import app
from tests.authkit import bearer, seed_user

AGENT_DIR = Path(__file__).resolve().parent.parent


# ---- error shape and request ids --------------------------------------------------------------------------------------
def test_every_error_has_code_message_and_request_id(client):
    seed_user("u_officer", "officer")
    h = bearer("u_officer")
    cases = [
        (client.get("/agent/runs/nope", headers=h), 404, "not_found"),
        (client.get("/no/such/route", headers=h), 404, "not_found"),
        (client.get("/approvals"), 401, "unauthorized"),
        (client.post("/auth/profile", headers=h, json={"requested_role": "king"}), 422, "validation_error"),
        (client.delete("/approvals", headers=h), 405, "method_not_allowed"),
    ]
    for r, status, code in cases:
        body = r.json()
        assert r.status_code == status, (r.request.url, r.text)
        assert set(body) == {"error", "request_id"} and set(body["error"]) == {"code", "message"}
        assert body["error"]["code"] == code and body["error"]["message"]
        assert body["request_id"] == r.headers["x-request-id"]
    assert client.get("/approvals").headers["www-authenticate"] == "Bearer"


def test_unexpected_errors_are_a_clean_500_without_internals(client, monkeypatch):
    seed_user("u_officer", "officer")
    monkeypatch.setattr(approvals, "list_approvals", lambda status: 1 / 0)
    r = TestClient(app, raise_server_exceptions=False).get("/approvals", headers=bearer("u_officer"))
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error" and "ZeroDivision" not in r.text and "Traceback" not in r.text
    assert r.json()["request_id"] == r.headers["x-request-id"]


def test_request_id_is_echoed_when_sane_and_replaced_when_not():
    c = TestClient(app)
    assert c.get("/health", headers={"X-Request-ID": "abc-12345678"}).headers["x-request-id"] == "abc-12345678"
    for bad in ("short", "has spaces in it!!", "x" * 200, "semi;colon-12345"):
        rid = c.get("/health", headers={"X-Request-ID": bad}).headers["x-request-id"]
        assert rid != bad and re.fullmatch(r"[0-9a-f]{32}", rid)
    assert c.get("/health").headers["x-request-id"] != c.get("/health").headers["x-request-id"]


def test_health_is_unchanged():
    assert TestClient(app).get("/health").json() == {"ok": True, "service": "agent", "stubs": config.USE_STUBS}


# ---- readiness -----------------------------------------------------------------------------------------------------
def test_ready_reports_the_database_and_auth_state():
    c = TestClient(app)
    r = c.get("/ready")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    assert r.json() == {"ok": True, "service": "agent", "database": "sqlite", "auth_required": False}


def test_ready_is_503_when_auth_is_required_but_not_configured(monkeypatch):
    monkeypatch.setattr(config, "AUTH_REQUIRED", True)
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", "")
    monkeypatch.setattr(config, "SUPABASE_URL", "")
    r = TestClient(app).get("/ready")
    assert r.status_code == 503 and r.json()["ok"] is False and "SUPABASE" in r.json()["problems"][0]


def test_ready_is_503_when_the_database_is_down(monkeypatch):
    monkeypatch.setattr(db, "ping", lambda: (_ for _ in ()).throw(RuntimeError("down")))
    r = TestClient(app).get("/ready")
    assert r.status_code == 503 and "database unreachable" in r.json()["problems"][0]


# ---- logs ----------------------------------------------------------------------------------------------------------
def test_access_log_is_structured_and_never_contains_the_query_string(caplog):
    caplog.set_level(logging.INFO, logger="trueclose.access")
    r = TestClient(app).get("/health?access_token=SECRET-VALUE")
    rec = [x for x in caplog.records if x.name == "trueclose.access"][-1]
    assert rec.request_id == r.headers["x-request-id"] and rec.path == "/health" and rec.status == 200 and rec.method == "GET"
    line = json.loads(http_utils.JsonFormatter().format(rec))
    assert {"ts", "level", "msg", "request_id", "method", "path", "status", "ms"} <= set(line)
    assert "SECRET-VALUE" not in json.dumps(line)


def test_access_log_names_the_signed_in_user(client, caplog):
    seed_user("u_officer", "officer")
    caplog.set_level(logging.INFO, logger="trueclose.access")
    client.get("/approvals", headers=bearer("u_officer"))
    assert [x for x in caplog.records if x.name == "trueclose.access"][-1].user == "u_officer"


# ---- CORS ----------------------------------------------------------------------------------------------------------
def _preflight(env_origins: str | None, origin: str) -> str | None:
    headers = {"Origin": origin, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"}
    code = ("from fastapi.testclient import TestClient\nfrom app.main import app\n"
            f"r = TestClient(app).options('/approvals', headers={headers!r})\n"
            "print(r.headers.get('access-control-allow-origin'))")
    import os
    env = {**os.environ, "CORS_ORIGINS": env_origins or ""}
    out = subprocess.run([sys.executable, "-c", code], cwd=AGENT_DIR, env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip().splitlines()[-1]


def test_cors_allowlist_is_enforced_when_set_and_open_only_when_unset():
    allow = "https://trueclose-neon.vercel.app,http://localhost:5174"
    assert _preflight(allow, "https://trueclose-neon.vercel.app") == "https://trueclose-neon.vercel.app"
    assert _preflight(allow, "https://evil.example") == "None"
    assert _preflight(None, "https://anything.example") == "*"


# ---- database adapter ----------------------------------------------------------------------------------------------
def test_sqlite_dialect_is_translated_for_postgres():
    sql, ret = db.translate_sql("INSERT OR REPLACE INTO kv (k, v) VALUES ('telegram_offset', ?)")
    assert sql == "INSERT INTO kv (k, v) VALUES ('telegram_offset', %s) ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v" and not ret
    sql, _ = db.translate_sql("INSERT OR REPLACE INTO citizen_requests (ticket_id, chat_id, status) VALUES (?,?, 'registered')")
    assert "ON CONFLICT (ticket_id) DO UPDATE SET chat_id=EXCLUDED.chat_id, status=EXCLUDED.status" in sql and "%s,%s" in sql
    sql, ret = db.translate_sql("INSERT INTO audit (ts, event, prev_hash, hash) VALUES (?,?,?,?)")
    assert sql.endswith("RETURNING idx") and ret is True
    assert db.translate_sql("SELECT * FROM approvals WHERE approval_id=?") == ("SELECT * FROM approvals WHERE approval_id=%s", False)
    assert db.translate_sql("UPDATE runs SET status=? WHERE run_id=?")[0] == "UPDATE runs SET status=%s WHERE run_id=%s"


def _fake_psycopg(monkeypatch):
    class Operational(Exception):
        pass

    class Cur:
        description = [1]

        def __init__(self, rows):
            self.rows = rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

        def fetchall(self):
            return self.rows

    class Conn:
        def __init__(self):
            self.log, self.commits, self.rollbacks, self.fail_next, self.fail_with = [], 0, 0, False, None

        def execute(self, sql, params=()):
            if self.fail_next:
                self.fail_next = False
                raise self.fail_with
            self.log.append((sql, params))
            return Cur([{"idx": 7}] if "RETURNING idx" in sql else [{"n": 1}])

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            pass

    made = []
    pg, rows = types.ModuleType("psycopg"), types.ModuleType("psycopg.rows")
    pg.OperationalError = Operational
    pg.connect = lambda url, **kw: made.append(Conn()) or made[-1]
    rows.dict_row = object()
    pg.rows = rows
    monkeypatch.setitem(sys.modules, "psycopg", pg)
    monkeypatch.setitem(sys.modules, "psycopg.rows", rows)
    return made, Operational


def test_postgres_mode_translates_returns_the_audit_index_and_never_creates_tables(monkeypatch):
    made, _ = _fake_psycopg(monkeypatch)
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://user:pw@host/db")
    db.reset()
    conn = db.get_conn()
    assert isinstance(conn, db.PgConnection) and db.is_postgres()
    cur = conn.execute("INSERT INTO audit (ts, event, prev_hash, hash) VALUES (?,?,?,?)", ("t", "e", "p", "h"))
    assert cur.lastrowid == 7
    sql, params = made[0].log[-1]
    assert "%s" in sql and "?" not in sql and sql.endswith("RETURNING idx") and params == ("t", "e", "p", "h")
    assert conn.execute("SELECT 1").fetchone() == {"n": 1}
    conn.commit()
    assert made[0].commits == 1
    # the application only reads and writes rows: no CREATE / ALTER / DROP ever reaches the server
    assert not [s for s, _ in made[0].log if re.match(r"\s*(CREATE|ALTER|DROP)\b", s, re.I)]
    assert db.ping() == "postgres"


def test_postgres_connection_reconnects_once_and_rolls_back_failed_statements(monkeypatch):
    made, Operational = _fake_psycopg(monkeypatch)
    conn = db.PgConnection("postgresql://x")
    made[0].fail_next, made[0].fail_with = True, Operational("server closed the connection")
    assert conn.execute("SELECT 1").fetchone() == {"n": 1}
    assert len(made) == 2                                              # one reconnect, then the statement ran
    made[1].fail_next, made[1].fail_with = True, ValueError("constraint violated")
    with pytest.raises(ValueError):
        conn.execute("SELECT 2")
    assert made[1].rollbacks == 1                                      # a failed statement must not poison the next
    assert conn.execute("SELECT 3").fetchone() == {"n": 1}


def test_postgres_schema_file_covers_every_table_the_sqlite_schema_has():
    tables = lambda p: set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", (AGENT_DIR / "sql" / p).read_text()))
    assert tables("schema_postgres.sql") == tables("schema.sql")
    pg = (AGENT_DIR / "sql" / "schema_postgres.sql").read_text()
    for t in tables("schema.sql"):
        assert f"ALTER TABLE {t}" in re.sub(r"\s+", " ", pg).replace("  ", " ") or re.search(rf"ALTER TABLE {t}\s+ENABLE ROW LEVEL SECURITY", pg), t


def test_existing_sqlite_files_get_the_new_approval_columns(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("CREATE TABLE approvals (approval_id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL, run_id TEXT, action TEXT NOT NULL,"
                      " verdict_snapshot TEXT NOT NULL, status TEXT NOT NULL, note TEXT, engine_result TEXT, created_at TEXT NOT NULL,"
                      " decided_at TEXT);")
    old.close()
    db.reset(str(path))
    cols = {r[1] for r in db.get_conn().execute("PRAGMA table_info(approvals)").fetchall()}
    assert {"actor", "actor_email"} <= cols


def test_committed_openapi_file_matches_the_app():
    """agent/openapi.json is what the web client's types are generated from: regenerate it with scripts/export_openapi.py."""
    committed = json.loads((AGENT_DIR / "openapi.json").read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(app.openapi())), "run: python scripts/export_openapi.py"


def test_postgres_cursor_can_be_looped_over_like_a_sqlite_cursor():
    """cases.tracked_tickets does `for r in conn.execute(...)`; on Postgres that raised TypeError and the watcher never ran."""
    class FakeCursor:
        description = [("ticket_id",)]
        def fetchall(self): return [{"ticket_id": "a"}, {"ticket_id": "b"}]
        def fetchone(self): return None
    assert [r["ticket_id"] for r in db._PgCursor(FakeCursor())] == ["a", "b"]
    class NoRows:
        description = None
    assert list(db._PgCursor(NoRows())) == []
