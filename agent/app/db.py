"""SQLite storage via plain sqlite3. Schema lives in agent/sql/schema.sql (human-reviewed)."""
import sqlite3
import threading
from pathlib import Path
from . import config

_SCHEMA = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(_SCHEMA.read_text())
    return _conn


def lock() -> threading.RLock:
    return _lock


def reset(path: str | None = None) -> None:
    """Close and reopen the connection on next use (tests pass ':memory:')."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None
    if path:
        config.DB_PATH = path
