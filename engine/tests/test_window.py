"""window_days: tickets raised in the last N days of the data, counted back from each city's own latest ticket."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import main
from app.store import WarehouseStore


def row(i, city, created, status="closed", ward="W1", cat="pothole"):
    return {"ticket_id": f"{city[:3]}-{i}", "city": city, "data_quality": "real", "source": "test", "category": cat, "text": "x",
            "lang": "en", "lat": 12.9, "lng": 77.6, "h3": None, "location_precision": "exact", "ward": ward, "created_at": created,
            "closed_at": None, "closed_by_hash": None, "status": status, "closure_note": None, "closure_photo_url": None}


@pytest.fixture
def warehouse(tmp_path):
    # Bengaluru data ends 2025-06-19; Mumbai ends much later (2026-10-24), so "last 30 days" differs per city
    blr = [row(1, "bengaluru", "2025-06-19T07:00:00Z"), row(2, "bengaluru", "2025-06-01T07:00:00Z"), row(3, "bengaluru", "2025-04-01T07:00:00Z", status="reopened"),
           row(4, "bengaluru", "2024-09-15T07:00:00Z"), row(5, "bengaluru", "2024-12-01T07:00:00Z")]
    mum = [row(1, "mumbai", "2026-10-24T06:00:00Z"), row(2, "mumbai", "2026-10-10T06:00:00Z"), row(3, "mumbai", "2026-03-18T06:00:00Z")]
    pd.DataFrame(blr).to_parquet(tmp_path / "tickets_bengaluru.parquet", index=False)
    pd.DataFrame(mum).to_parquet(tmp_path / "tickets_mumbai.parquet", index=False)
    return tmp_path


@pytest.fixture
def client(warehouse, monkeypatch):
    monkeypatch.setattr(main, "store", WarehouseStore(warehouse))
    return TestClient(main.app)


def ids(client, **params):
    return sorted(x["ticket"]["ticket_id"] for x in client.get("/tickets", params=params).json())


def test_no_window_returns_everything(client):
    assert len(ids(client)) == 8


def test_window_counts_back_from_each_citys_own_latest_ticket_not_from_today(client):
    # last 30 days: Bengaluru from 2025-05-20 (tickets 1 and 2), Mumbai from 2026-09-24 (tickets 1 and 2)
    assert ids(client, window_days=30) == ["ben-1", "ben-2", "mum-1", "mum-2"]


def test_window_with_a_city_filter(client):
    assert ids(client, window_days=30, city="mumbai") == ["mum-1", "mum-2"]
    assert ids(client, window_days=90, city="bengaluru") == ["ben-1", "ben-2", "ben-3"]   # back to 2025-03-21


def test_a_longer_window_never_returns_fewer_tickets(client):
    a, b, c = (len(ids(client, window_days=d)) for d in (30, 90, 180))
    assert a <= b <= c


def test_cities_reports_the_span_and_windowed_counts(client):
    full = {c["city"]: c for c in client.get("/cities").json()}
    assert full["bengaluru"]["tickets"] == 5 and full["bengaluru"]["data_as_of"] == "2025-06-19T07:00:00Z"
    assert full["bengaluru"]["data_from"] == "2024-09-15T07:00:00Z"
    win = {c["city"]: c for c in client.get("/cities", params={"window_days": 30}).json()}
    assert win["bengaluru"]["tickets"] == 2 and win["mumbai"]["tickets"] == 2
    assert win["bengaluru"]["data_as_of"] == full["bengaluru"]["data_as_of"]   # the span does not shrink with the window


def test_ward_stats_map_and_hotspot_inputs_follow_the_window(client):
    all_rows = client.get("/wards/stats", params={"city": "bengaluru"}).json()
    win_rows = client.get("/wards/stats", params={"city": "bengaluru", "window_days": 30}).json()
    assert sum(r["tickets"] for r in all_rows) == 5 and sum(r["tickets"] for r in win_rows) == 2
    assert main.store.reopen_groups(30) != [] and sum(g["done"] for g in main.store.reopen_groups(30) if g["city"] == "bengaluru" and g["kind"] == "ward") == 2


def test_window_days_is_validated(client):
    assert client.get("/tickets", params={"window_days": 0}).status_code == 422
    assert client.get("/tickets", params={"window_days": 99999}).status_code == 422


def test_bengaluru_from_trims_old_bengaluru_rows_only(warehouse, monkeypatch):
    monkeypatch.setenv("ENGINE_BENGALURU_FROM", "2024-10-01")
    store = WarehouseStore(warehouse)
    cities = {c["city"]: c["tickets"] for c in store.cities()}
    assert cities == {"bengaluru": 4, "mumbai": 3}      # the 2024-09-15 ticket is gone, Mumbai is untouched
    assert store.get_ticket("ben-4") is None


def test_bengaluru_from_must_be_a_date(warehouse, monkeypatch):
    monkeypatch.setenv("ENGINE_BENGALURU_FROM", "last year")
    with pytest.raises(ValueError):
        WarehouseStore(warehouse)
