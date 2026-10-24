"""ENGINE_DUCKDB_PATH / ENGINE_MEMORY_LIMIT / ENGINE_THREADS: where the DuckDB tables live, never what they contain."""
import pytest

from app import store


def test_default_is_an_in_memory_database(monkeypatch):
    for k in ("ENGINE_DUCKDB_PATH", "ENGINE_MEMORY_LIMIT", "ENGINE_THREADS"):
        monkeypatch.delenv(k, raising=False)
    con = store._connect()
    con.execute("create table t as select 1 as n")
    assert con.execute("select n from t").fetchone() == (1,)


def test_file_backed_database_with_a_memory_limit(monkeypatch, tmp_path):
    path = tmp_path / "scratch.duckdb"
    path.write_bytes(b"stale file from an earlier run")   # a leftover file must not break startup
    monkeypatch.setenv("ENGINE_DUCKDB_PATH", str(path))
    monkeypatch.setenv("ENGINE_MEMORY_LIMIT", "120MB")
    monkeypatch.setenv("ENGINE_THREADS", "2")
    con = store._connect()
    con.execute("create table t as select range as n from range(1000)")
    assert con.execute("select count(*) from t").fetchone() == (1000,)
    assert path.exists()
    assert "MiB" in con.execute("select current_setting('memory_limit')").fetchone()[0] or "MB" in con.execute("select current_setting('memory_limit')").fetchone()[0]
    assert con.execute("select current_setting('threads')").fetchone()[0] == 2


@pytest.mark.parametrize("bad", ["lots", "200", "1TB; drop table x", "-5MB"])
def test_a_malformed_memory_limit_is_refused(monkeypatch, bad):
    monkeypatch.setenv("ENGINE_MEMORY_LIMIT", bad)
    with pytest.raises(ValueError):
        store._connect()
