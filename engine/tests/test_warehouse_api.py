"""API tests against a small Parquet warehouse built in a temp dir (no real data needed)."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import main
from app.store import WarehouseStore


def t(i, city="mumbai", cat="garbage", status="closed", prec="exact", ward="HW", day=1, dq="real"):
    return {"ticket_id": f"{city[:3]}-{i}", "city": city, "data_quality": dq, "source": "test", "category": cat,
            "text": "x", "lang": "other", "lat": 19.05 if prec in ("exact", "generated") else None,
            "lng": 72.85 if prec in ("exact", "generated") else None, "h3": None, "location_precision": prec,
            "ward": ward, "created_at": f"2026-04-{day:02d}T10:00:00Z", "closed_at": None, "closed_by_hash": None,
            "status": status, "closure_note": None, "closure_photo_url": None}


@pytest.fixture
def client(tmp_path, monkeypatch):
    rows_m = [t(1, day=1), t(2, cat="pothole", day=2), t(3, status="open", day=3), t(4, status="reopened", day=4),
              t(5, ward="KW", day=5)]
    rows_b = [t(1, city="bengaluru", cat="garbage", prec="ward_centroid", ward="Jakkur", dq="partial", day=6),
              t(2, city="bengaluru", cat="streetlight", prec="none", ward="Someshwara", dq="partial", day=7)]
    pd.DataFrame(rows_m).assign(channel="1916").to_parquet(tmp_path / "tickets_mumbai.parquet", index=False)
    pd.DataFrame(rows_b).assign(raw_status="Closed").to_parquet(tmp_path / "tickets_bengaluru.parquet", index=False)
    monkeypatch.setattr(main, "store", WarehouseStore(tmp_path))
    return TestClient(main.app)


def test_health_reports_warehouse_mode(client):
    assert client.get("/health").json()["mode"] == "warehouse"


def test_union_of_cities_with_different_extra_columns(client):
    assert len(client.get("/tickets").json()) == 7


def test_newest_first_and_filters(client):
    ids = [x["ticket"]["ticket_id"] for x in client.get("/tickets").json()]
    assert ids[0] == "ben-2" and ids[-1] == "mum-1"
    assert len(client.get("/tickets", params={"city": "mumbai"}).json()) == 5
    assert len(client.get("/tickets", params={"city": "mumbai", "status": "open"}).json()) == 1
    assert len(client.get("/tickets", params={"category": "pothole"}).json()) == 1
    assert len(client.get("/tickets", params={"ward": "KW"}).json()) == 1


def test_paging(client):
    page1 = client.get("/tickets", params={"limit": 3}).json()
    page2 = client.get("/tickets", params={"limit": 3, "offset": 3}).json()
    assert len(page1) == 3 and len(page2) == 3
    assert not {x["ticket"]["ticket_id"] for x in page1} & {x["ticket"]["ticket_id"] for x in page2}


def test_real_tickets_get_a_labelled_baseline_not_a_made_up_score(client):
    s = client.get("/tickets/mum-1/score").json()
    assert s["model_version"] == "baseline-no-model" and s["p_false_closure"] == 0.5 and s["reasons"] == []
    assert client.get("/tickets", params={"min_score": 0.7}).json() == []


def test_ward_level_tickets_serialise_with_null_location(client):
    x = client.get("/tickets/ben-2").json()
    assert x["lat"] is None and x["h3"] is None and x["location_precision"] == "none"


@pytest.mark.parametrize("tid,eligible,cost", [
    ("mum-1", True, 3),     # garbage, exact point: eligible, but the verifier is not built, so inconclusive
    ("mum-2", False, 0),    # pothole: below satellite resolution
    ("ben-1", False, 0),    # garbage but ward-level only
])
def test_satellite_eligibility_is_honest(client, tid, eligible, cost):
    ev = client.post("/satellite/check", json={"ticket_id": tid}).json()
    assert ev["verdict"] == "inconclusive" and ev["likelihood_ratio"] == 1.0
    assert ev["details"]["eligible"] is eligible and ev["cost"] == cost
    assert client.get(f"/tickets/{tid}/score").json()["satellite_eligible"] is eligible
    if eligible:
        assert ev["details"]["stub"] is True


def test_ward_stats_numbers(client):
    rows = {(r["ward"], r["category"]): r for r in client.get("/wards/stats", params={"city": "mumbai"}).json()}
    hw = rows[("HW", "garbage")]
    # HW garbage: closed(1), open(1), reopened(1) -> 3 tickets, 2 no longer open
    assert (hw["tickets"], hw["closed"], hw["open"], hw["reopened"]) == (3, 1, 1, 1)
    assert hw["official_rate"] == round(2 / 3, 4) and hw["reopen_rate"] == 0.5 and hw["honest_rate"] is None


def test_cities_summary(client):
    by = {c["city"]: c for c in client.get("/cities").json()}
    assert by["mumbai"]["tickets"] == 5 and by["bengaluru"]["data_quality"] == "partial"


def test_reopen_flows_through_lists_filters_and_stats(client):
    assert client.post("/muni/tickets/mum-1/reopen").json()["status"] == "reopened"
    assert client.get("/tickets/mum-1").json()["status"] == "reopened"
    reopened = client.get("/tickets", params={"city": "mumbai", "status": "reopened"}).json()
    assert {x["ticket"]["ticket_id"] for x in reopened} == {"mum-1", "mum-4"}
    hw = next(r for r in client.get("/wards/stats", params={"city": "mumbai", "category": "garbage"}).json() if r["ward"] == "HW")
    assert hw["reopened"] == 2 and hw["closed"] == 0
    client.post("/muni/tickets/mum-1/reopen")  # reopening twice must not duplicate the override
    assert len(client.get("/tickets", params={"city": "mumbai", "status": "reopened"}).json()) == 2


def test_unknown_ticket_and_connector(client):
    assert client.get("/tickets/nope").status_code == 404
    assert client.post("/satellite/check", json={"ticket_id": "nope"}).status_code == 404
    assert client.post("/connectors/atlantis/sync").status_code == 404
