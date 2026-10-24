"""Regression tests for the Engine bugs found in the backend review."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import main
from app.store import WarehouseStore


def row(i, status="closed"):
    return {"ticket_id": f"mum-{i}", "city": "mumbai", "data_quality": "real", "source": "test", "category": "garbage",
            "text": "x", "lang": "other", "lat": 19.05, "lng": 72.85, "h3": None, "location_precision": "exact",
            "ward": "HW", "created_at": "2026-04-01T10:00:00Z", "closed_at": None, "closed_by_hash": None,
            "status": status, "closure_note": None, "closure_photo_url": None}


@pytest.fixture
def env(tmp_path, monkeypatch):
    pd.DataFrame([row(1), row(2, "open"), row(3, "reopened")]).to_parquet(tmp_path / "tickets_mumbai.parquet", index=False)
    monkeypatch.setattr(main, "store", WarehouseStore(tmp_path))
    return TestClient(main.app), tmp_path


def test_only_a_closed_ticket_can_be_reopened(env):
    client, _ = env
    assert client.post("/muni/tickets/mum-1/reopen").status_code == 200
    assert client.get("/tickets/mum-1").json()["status"] == "reopened"
    assert client.post("/muni/tickets/mum-1/reopen").status_code == 409     # already reopened
    r = client.post("/muni/tickets/mum-2/reopen")                            # open
    assert r.status_code == 409 and "only a closed ticket" in r.json()["error"]["message"]
    assert client.get("/tickets/mum-2").json()["status"] == "open"           # and nothing changed
    assert client.post("/muni/tickets/mum-3/reopen").status_code == 409      # reopened already


def test_reopens_survive_an_engine_restart(env, monkeypatch):
    client, directory = env
    assert client.post("/muni/tickets/mum-1/reopen").status_code == 200
    monkeypatch.setattr(main, "store", WarehouseStore(directory))            # a fresh process
    assert TestClient(main.app).get("/tickets/mum-1").json()["status"] == "reopened"


def test_sync_needs_the_admin_token_when_one_is_set(env, monkeypatch):
    client, _ = env
    monkeypatch.setenv("ENGINE_ADMIN_TOKEN", "s3cret")
    assert client.post("/connectors/mumbai/sync").status_code == 403
    assert client.post("/connectors/nope/sync", headers={"X-Admin-Token": "s3cret"}).status_code == 404   # passed auth


def test_a_second_sync_while_one_runs_is_refused(env):
    client, _ = env
    assert main._sync_lock.acquire(blocking=False)
    try:
        assert client.post("/connectors/mumbai/sync").status_code == 409
    finally:
        main._sync_lock.release()


@pytest.mark.parametrize("value", ["-0.1", "1.5", "abc"])
def test_min_score_must_be_between_0_and_1(env, value):
    client, _ = env
    assert client.get("/tickets", params={"min_score": value}).status_code == 422
    assert client.get("/tickets", params={"min_score": "0.5"}).status_code == 200
