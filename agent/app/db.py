"""Storage. SQLite (plain sqlite3) is the default for local runs and tests; Postgres is used when DATABASE_URL is set.

Postgres mode never creates tables: a person runs agent/sql/schema_postgres.sql once (Supabase SQL editor). The thin
adapter below lets every existing call site keep using `get_conn().execute("... ? ...", params)`, `.fetchone()`,
`.fetchall()`, `.commit()` and `cur.lastrowid`.
"""
import re
import sqlite3
import threading
import time
from pathlib import Path
from . import config

_SCHEMA = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
_lock = threading.RLock()
_conn = None   # sqlite3.Connection or PgConnection

# INSERT OR REPLACE (SQLite) becomes an upsert on these primary keys in Postgres
_UPSERT_KEYS = {"kv": "k", "citizen_requests": "ticket_id"}
_INSERT_OR_REPLACE = re.compile(r"^\s*INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]*)\)\s*(VALUES.*)$", re.I | re.S)

# columns added after the first release of a table; applied to existing SQLite files only (Postgres uses the schema file)
_SQLITE_ADDED_COLUMNS = {
    "approvals": [("actor", "TEXT"), ("actor_email", "TEXT")],
}


def translate_sql(sql: str) -> tuple[str, bool]:
    """SQLite dialect -> Postgres. Returns (sql, wants_returning_idx)."""
    returning = False
    m = _INSERT_OR_REPLACE.match(sql)
    if m:
        table, cols, rest = m.group(1), [c.strip() for c in m.group(2).split(",")], m.group(3)
        key = _UPSERT_KEYS[table]
        sets = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != key)
        sql = f"INSERT INTO {table} ({', '.join(cols)}) {rest} ON CONFLICT ({key}) DO UPDATE SET {sets}"
    if re.match(r"^\s*INSERT\s+INTO\s+audit\b", sql, re.I) and "RETURNING" not in sql.upper():
        sql, returning = sql.rstrip().rstrip(";") + " RETURNING idx", True
    return sql.replace("?", "%s"), returning


class _PgCursor:
    def __init__(self, cur, lastrowid=None, rows=None):
        self._cur, self.lastrowid, self._rows = cur, lastrowid, rows   # rows: already fetched (a read that released its lock)

    def fetchone(self):
        if self._rows is not None:
            return self._rows.pop(0) if self._rows else None
        return self._cur.fetchone() if self._cur.description else None

    def fetchall(self):
        if self._rows is not None:
            rows, self._rows = self._rows, []
            return rows
        return self._cur.fetchall() if self._cur.description else []

    def __iter__(self):
        # sqlite3 cursors can be looped over directly; code written against SQLite does `for r in conn.execute(...)`
        return iter(self.fetchall())


class PgConnection:
    """One shared psycopg connection guarded by the module lock, reconnecting once if the server dropped it."""

    def __init__(self, url: str):
        self.url = url
        self._c = None
        self._dirty = False   # True while this connection holds uncommitted writes
        self._connect()

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row
        self._c = psycopg.connect(self.url, row_factory=dict_row, autocommit=False)

    def execute(self, sql: str, params=()):
        import psycopg
        sql, returning = translate_sql(sql)
        for attempt in (0, 1):
            try:
                cur = self._c.execute(sql, tuple(params))
                last = cur.fetchone()["idx"] if returning else None
                if sql.lstrip()[:6].upper() != "SELECT" or returning:
                    self._dirty = True
                elif not self._dirty:
                    # A read with nothing pending: fetch it and end the transaction now. Left open, the connection sits
                    # "idle in transaction" holding a lock that blocks schema changes and everything queued behind them.
                    rows = cur.fetchall() if cur.description else []
                    self._c.rollback()
                    return _PgCursor(cur, last, rows)
                return _PgCursor(cur, last)
            except psycopg.OperationalError:
                if attempt:
                    raise
                self._connect()
            except Exception:
                self._c.rollback()   # a failed statement must not poison the next one
                self._dirty = False
                raise

    def commit(self):
        self._c.commit()
        self._dirty = False

    def close(self):
        if self._c is not None:
            self._c.close()


def is_postgres() -> bool:
    return bool(config.DATABASE_URL)


def _migrate_sqlite(conn: sqlite3.Connection) -> None:
    for table, cols in _SQLITE_ADDED_COLUMNS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, typ in cols:
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
    conn.commit()


def _retire_old_tables(conn: sqlite3.Connection) -> None:
    """A local database made by an earlier build of the Agent had its own `users` and an older `user_tickets` (no
    `linked_by`). The current schema would silently keep the old table and then fail on the first insert, so the old
    one is set aside under another name (never deleted) and the schema creates a fresh one."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(user_tickets)").fetchall()}
    if cols and "linked_by" not in cols:
        conn.execute(f"ALTER TABLE user_tickets RENAME TO user_tickets_old_{int(time.time())}")
        conn.commit()


def get_conn():
    global _conn
    if _conn is None:
        if is_postgres():
            _conn = PgConnection(config.DATABASE_URL)   # tables come from agent/sql/schema_postgres.sql
        else:
            _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _retire_old_tables(_conn)
            _conn.executescript(_SCHEMA.read_text())
            _migrate_sqlite(_conn)
    return _conn


def lock() -> threading.RLock:
    return _lock


def ping() -> str:
    """Raise if the database cannot answer; return the backend name. Used by /ready."""
    with _lock:
        get_conn().execute("SELECT 1").fetchone()
    return "postgres" if is_postgres() else "sqlite"


def reset(path: str | None = None) -> None:
    """Close and reopen the connection on next use (tests pass ':memory:')."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None
    if path:
        config.DB_PATH = path
