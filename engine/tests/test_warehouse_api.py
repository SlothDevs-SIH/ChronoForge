"""API tests against a small Parquet warehouse built in a temp dir (no real data needed)."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import main
from app.store import WarehouseStore


def t(i, city="mumbai", cat="garbage", status="closed", prec="exact", ward="HW", day=1, dq="real", text="x"):
    return {"ticket_id": f"{city[:3]}-{i}", "city": city, "data_quality": dq, "source": "test", "category": cat,
            "text": text, "lang": "other", "lat": 19.05 if prec in ("exact", "generated") else None,
            "lng": 72.85 if prec in ("exact", "generated") else None, "h3": None, "location_precision": prec,
            "ward": ward, "created_at": f"2026-04-{day:02d}T10:00:00Z",
            "closed_at": f"2026-04-{day:02d}T20:00:00Z" if status in ("closed", "reopened") else None, "closed_by_hash": None,
            "status": status, "closure_note": None, "closure_photo_url": None}


@pytest.fixture
def client(tmp_path, monkeypatch):
    rows_m = [t(1, text="Illegal Dumping", day=1), t(2, cat="pothole", day=2), t(3, status="open", day=3, text="Illegal Dumping"), t(4, status="reopened", day=4),
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


@pytest.mark.parametrize("tid,eligible", [
    ("mum-1", True),     # illegal dumping, exact point, has a closing date
    ("mum-2", False),    # pothole: below satellite resolution
    ("ben-1", False),    # garbage but ward-level only
    ("mum-3", False),    # large-area wording and exact point, but still open: no closing date, no "after"
    ("mum-5", False),    # garbage with no sign of scale: not applicable
])
def test_satellite_eligibility_is_honest(client, tid, eligible):
    # cached_only=True so the test never reads live imagery
    ev = client.post("/satellite/check", json={"ticket_id": tid, "cached_only": True}).json()
    assert ev["verdict"] == "inconclusive" and ev["likelihood_ratio"] == 1.0 and ev["cost"] == 0
    assert ev["details"]["eligible"] is eligible
    if eligible:
        assert ev["details"]["source"] == "not_cached" and ev["details"]["abstained"] is True
    else:
        assert ev["details"]["reason"]
    assert client.get(f"/tickets/{tid}/score").json()["satellite_eligible"] is (tid in ("mum-1", "mum-3"))


def test_open_ticket_reason_mentions_the_missing_closing_date(client):
    ev = client.post("/satellite/check", json={"ticket_id": "mum-3", "cached_only": True}).json()
    assert "closing date" in ev["details"]["reason"]


def test_chip_endpoint_rejects_bad_ids_and_missing_chips(client):
    assert client.get("/satellite/chip/mum-1/before.png").status_code == 404
    assert client.get("/satellite/chip/..%2Fsecret/before.png").status_code == 404
    assert client.get("/satellite/chip/mum-1/sideways.png").status_code == 422


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


# ---------------- scored tickets ----------------
def scored_dir(tmp_path):
    return tmp_path


@pytest.fixture
def scored(tmp_path, monkeypatch):
    rows = [t(1, day=1), t(2, day=2), t(3, day=3), t(4, city="bengaluru", cat="garbage", prec="ward_centroid", dq="partial", day=4)]
    pd.DataFrame(rows[:3]).to_parquet(tmp_path / "tickets_mumbai.parquet", index=False)
    pd.DataFrame(rows[3:]).to_parquet(tmp_path / "tickets_bengaluru.parquet", index=False)
    cols = dict(risk_percentile=float("nan"), flags="")
    pd.DataFrame([
        dict(ticket_id="mum-1", p_false_closure=0.678, score_type="rule_flags", model_version="mum-flags-v1", **{**cols, "flags": "citizen_image_only"}),
        dict(ticket_id="mum-2", p_false_closure=0.5, score_type="rule_flags", model_version="mum-flags-v1", **cols),
    ]).to_parquet(tmp_path / "scores_mumbai.parquet", index=False)
    pd.DataFrame([dict(ticket_id="ben-4", p_false_closure=0.64, score_type="risk_rank_prior", model_version="blr-reopen-v1",
                       risk_percentile=0.85, flags="")]).to_parquet(tmp_path / "scores_bengaluru.parquet", index=False)
    monkeypatch.setattr(main, "store", WarehouseStore(tmp_path))
    return TestClient(main.app)


def test_scores_carry_type_percentile_and_flags(scored):
    m = scored.get("/tickets/mum-1/score").json()
    assert m["score_type"] == "rule_flags" and m["p_false_closure"] == 0.678 and m["flags"] == ["citizen_image_only"]
    assert m["reasons"] and m["reasons"][0]["feature"] == "citizen_image_only"
    b = scored.get("/tickets/ben-4/score").json()
    assert b["score_type"] == "risk_rank_prior" and b["risk_percentile"] == 0.85 and b["model_version"] == "blr-reopen-v1"


def test_unscored_ticket_falls_back_to_the_neutral_baseline(scored):
    s = scored.get("/tickets/mum-3/score").json()
    assert s["score_type"] == "baseline" and s["p_false_closure"] == 0.5 and s["model_version"] == "baseline-no-model"


def test_sort_by_risk_and_min_score(scored):
    ids = [x["ticket"]["ticket_id"] for x in scored.get("/tickets", params={"sort": "risk"}).json()]
    assert ids[0] == "mum-1" and ids[1] == "ben-4"
    newest = [x["ticket"]["ticket_id"] for x in scored.get("/tickets").json()]
    assert newest[0] == "ben-4"                         # newest first by default
    high = scored.get("/tickets", params={"min_score": 0.6}).json()
    assert {x["ticket"]["ticket_id"] for x in high} == {"mum-1", "ben-4"}


def test_list_scores_have_no_reasons_but_score_endpoint_does(scored):
    listed = scored.get("/tickets", params={"sort": "risk", "limit": 1}).json()[0]["score"]
    assert listed["reasons"] == [] and listed["score_type"] == "rule_flags"


def test_eval_results_flag_placeholders_when_no_metrics_exist(tmp_path, monkeypatch, scored):
    from app.scorer import runtime
    monkeypatch.setattr(runtime, "MODELS", tmp_path / "none")
    monkeypatch.setattr(main, "store", WarehouseStore(scored_dir(tmp_path)))
    r = TestClient(main.app).get("/eval/results").json()
    assert r["is_placeholder"] is True and r["verifiers_are_placeholder"] is True and r["scorers"] == {}


def test_eval_results_separate_scorers_from_verifiers(tmp_path, monkeypatch, scored):
    import json
    from app.scorer import runtime
    models = tmp_path / "models"
    models.mkdir()
    for name in ("blr-reopen-v1", "satellite", "benchmark_v1"):
        (models / f"{name}.metrics.json").write_text(json.dumps({"model": name}), encoding="utf-8")
    monkeypatch.setattr(runtime, "MODELS", models)
    monkeypatch.setattr(main, "store", WarehouseStore(scored_dir(tmp_path)))
    r = TestClient(main.app).get("/eval/results").json()
    assert list(r["scorers"]) == ["blr-reopen-v1"] and set(r["verifiers"]) == {"satellite", "benchmark_v1"}
    assert r["verifiers_are_placeholder"] is False and r["is_placeholder"] is False and r["pending"]


def test_ward_map_endpoint_returns_dots_with_rates(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    dots = [{"ward": "W1", "lat": 12.9, "lng": 77.5, "tickets": 30, "official_rate": 0.9, "reopen_rate": 0.02}]
    monkeypatch.setattr(main.store, "ward_map", lambda city, window_days=None: dots if city == "bengaluru" else [], raising=False)
    c = TestClient(main.app)
    assert c.get("/wards/map", params={"city": "bengaluru"}).json() == dots
    assert c.get("/wards/map", params={"city": "nowhere"}).json() == []
    assert c.get("/wards/map").status_code == 422     # the city is required
