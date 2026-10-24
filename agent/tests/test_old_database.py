"""A database file made by an earlier build of the Agent opens cleanly and keeps its data."""
import sqlite3

from app import config, db


def test_old_user_tickets_table_is_set_aside_not_dropped(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.executescript("CREATE TABLE user_tickets (user_id TEXT NOT NULL, ticket_id TEXT NOT NULL, added_at TEXT NOT NULL, "
                      "PRIMARY KEY (user_id, ticket_id)); INSERT INTO user_tickets VALUES ('u','T-1','2026-10-01');")
    old.close()
    db.reset(path)
    config.DB_PATH = path
    conn = db.get_conn()
    conn.execute("INSERT INTO user_tickets (user_id, ticket_id, linked_by, created_at) VALUES ('u','T-2','admin','now')")   # works
    conn.commit()
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    kept = [n for n in names if n.startswith("user_tickets_old_")]
    assert len(kept) == 1 and conn.execute(f"SELECT ticket_id FROM {kept[0]}").fetchone()[0] == "T-1"   # old rows are kept
    db.reset(":memory:")
    config.DB_PATH = ":memory:"


def test_a_fresh_database_is_untouched(tmp_path):
    db.reset(str(tmp_path / "new.db"))
    config.DB_PATH = str(tmp_path / "new.db")
    names = {r[0] for r in db.get_conn().execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "user_tickets" in names and not [n for n in names if n.startswith("user_tickets_old_")]
    db.reset(":memory:")
    config.DB_PATH = ":memory:"
