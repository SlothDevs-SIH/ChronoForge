"""Hotspot detection and duplicate-request matching."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import insights, main
from app.store import WarehouseStore


def group(city, kind, key, done, reopened):
    return {"city": city, "kind": kind, "key": key, "done": done, "reopened": reopened}


# ---- hotspots ----------------------------------------------------------------------------------------------------
def test_a_ward_far_above_its_city_is_flagged_and_ordinary_ones_are_not():
    rows = [group("bengaluru", "ward", f"W{i}", 200, 4) for i in range(20)]      # a 2% city rate
    rows.append(group("bengaluru", "ward", "Hot", 200, 40))                       # 20%
    rows.append(group("bengaluru", "ward", "Slightly", 200, 7))                   # 3.5%: not different enough
    found = insights.hotspots(rows)
    assert [h["key"] for h in found] == ["Hot"] and found[0]["ratio"] > 5


def test_small_groups_are_never_flagged_however_extreme():
    rows = [group("c", "ward", f"W{i}", 200, 4) for i in range(10)] + [group("c", "ward", "Tiny", 5, 5)]
    assert insights.hotspots(rows) == []


def test_a_city_with_no_reopen_data_is_skipped():
    assert insights.hotspots([group("mumbai", "ward", f"W{i}", 200, 0) for i in range(5)]) == []


def test_many_groups_do_not_produce_lucky_flags():
    # 100 identical wards with identical counts: nothing can be flagged
    assert insights.hotspots([group("c", "ward", f"W{i}", 100, 5) for i in range(100)]) == []


def test_closers_are_judged_against_the_city_ward_rate():
    rows = [group("c", "ward", f"W{i}", 200, 4) for i in range(10)] + [group("c", "closer", "abc12345", 100, 25), group("c", "closer", "ok", 100, 2)]
    assert [h["key"] for h in insights.hotspots(rows) if h["kind"] == "closer"] == ["abc12345"]


# ---- duplicates --------------------------------------------------------------------------------------------------
CAND = [
    {"ticket_id": "web-1", "category": "pothole", "ward": "Kothrud", "text": "Deep pothole outside the school gate", "status": "open", "created_at": "t"},
    {"ticket_id": "web-2", "category": "pothole", "ward": "Baner", "text": "Deep pothole outside the school gate", "status": "open", "created_at": "t"},
    {"ticket_id": "web-3", "category": "garbage", "ward": "Kothrud", "text": "Deep pothole outside the school gate", "status": "open", "created_at": "t"},
    {"ticket_id": "web-4", "category": "pothole", "ward": "kothrud ", "text": "streetlight broken near temple", "status": "open", "created_at": "t"},
]


def test_same_problem_same_ward_same_category_is_found():
    got = insights.similar(CAND, category="pothole", ward="Kothrud", text="big pothole near school gate")
    assert [g["ticket_id"] for g in got] == ["web-1"]                     # not the other ward, category, or an unrelated text


def test_without_a_named_ward_nothing_is_called_a_duplicate():
    assert insights.similar(CAND, category="pothole", ward="", text="pothole school gate") == []
    assert insights.similar(CAND, category="pothole", ward="unspecified", text="pothole school gate") == []


def test_similarity_ignores_filler_words_and_case():
    assert insights.text_similarity("The POTHOLE is on the road", "pothole on road") == 1.0
    assert insights.text_similarity("pothole", "garbage") == 0.0


# ---- through the API ---------------------------------------------------------------------------------------------
@pytest.fixture
def env(tmp_path, monkeypatch):
    base = {"ticket_id": "mum-1", "city": "mumbai", "data_quality": "real", "source": "t", "category": "garbage", "text": "x",
            "lang": "other", "lat": 19.05, "lng": 72.85, "h3": None, "location_precision": "exact", "ward": "HW",
            "created_at": "2026-04-01T10:00:00Z", "closed_at": None, "closed_by_hash": None, "status": "closed",
            "closure_note": None, "closure_photo_url": None}
    pd.DataFrame([base]).to_parquet(tmp_path / "tickets_mumbai.parquet", index=False)
    monkeypatch.setattr(main, "store", WarehouseStore(tmp_path))
    return TestClient(main.app)


def test_similar_endpoint_finds_an_open_request_and_forgets_a_closed_one(env):
    first = env.post("/requests", json={"category": "pothole", "text": "Deep pothole outside the school gate", "ward": "Kothrud"}).json()
    got = env.get("/requests/similar", params={"category": "pothole", "text": "pothole near school gate", "ward": "Kothrud"}).json()
    assert [g["ticket_id"] for g in got] == [first["ticket_id"]]
    env.post(f"/muni/tickets/{first['ticket_id']}/close")
    assert env.get("/requests/similar", params={"category": "pothole", "text": "pothole near school gate", "ward": "Kothrud"}).json() == []


def test_hotspots_endpoint_answers_with_its_caveat(env):
    body = env.get("/insights/hotspots").json()
    assert body["hotspots"] == [] and "not who is at fault" in body["caveat"]
