"""Requests filed on the website: created open, closed by the simulated city, reopened, and kept across a restart."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import main
from app.store import WarehouseStore

BODY = {"category": "pothole", "text": "Deep pothole outside the school gate", "ward": "Kothrud"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    base = {"ticket_id": "mum-1", "city": "mumbai", "data_quality": "real", "source": "t", "category": "garbage", "text": "x",
            "lang": "other", "lat": 19.05, "lng": 72.85, "h3": None, "location_precision": "exact", "ward": "HW",
            "created_at": "2026-04-01T10:00:00Z", "closed_at": None, "closed_by_hash": None, "status": "closed",
            "closure_note": None, "closure_photo_url": None}
    pd.DataFrame([base]).to_parquet(tmp_path / "tickets_mumbai.parquet", index=False)
    monkeypatch.setattr(main, "store", WarehouseStore(tmp_path))
    return TestClient(main.app), tmp_path, monkeypatch


def test_request_lifecycle(env):
    c, _, _ = env
    t = c.post("/requests", json=BODY).json()
    assert t["ticket_id"] == "web-00001" and t["status"] == "open" and t["city"] == "web"
    assert c.post(f"/muni/tickets/{t['ticket_id']}/reopen").status_code == 409        # not closed yet
    assert c.post(f"/muni/tickets/{t['ticket_id']}/close").status_code == 200
    got = c.get(f"/tickets/{t['ticket_id']}").json()
    assert got["status"] == "closed" and got["closed_at"]
    assert c.post(f"/muni/tickets/{t['ticket_id']}/close").status_code == 409         # cannot close twice
    assert c.post(f"/muni/tickets/{t['ticket_id']}/reopen").status_code == 200
    assert c.get(f"/tickets/{t['ticket_id']}").json()["status"] == "reopened"


def test_only_website_requests_can_be_closed_and_text_is_required(env):
    c, _, _ = env
    assert c.post("/muni/tickets/mum-1/close").status_code == 409
    assert c.post("/requests", json={**BODY, "text": "hi"}).status_code == 422


def test_requests_survive_a_restart(env):
    c, directory, mp = env
    tid = c.post("/requests", json=BODY).json()["ticket_id"]
    c.post(f"/muni/tickets/{tid}/close")
    mp.setattr(main, "store", WarehouseStore(directory))
    again = TestClient(main.app)
    assert again.get(f"/tickets/{tid}").json()["status"] == "closed"
    assert again.post("/requests", json=BODY).json()["ticket_id"] == "web-00002"      # ids keep counting
