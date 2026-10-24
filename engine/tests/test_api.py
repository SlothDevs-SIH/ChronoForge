from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


def test_list_sorted_and_city_filter():
    r = c.get("/tickets").json()
    scores = [x["score"]["p_false_closure"] for x in r]
    assert scores == sorted(scores, reverse=True)
    pune = c.get("/tickets", params={"city": "pune"}).json()
    assert [x["ticket"]["ticket_id"] for x in pune] == ["pune-0001"]


def test_satellite_ineligible_is_free_and_inconclusive():
    ev = c.post("/satellite/check", json={"ticket_id": "blr-0001"}).json()
    assert ev["verdict"] == "inconclusive" and ev["cost"] == 0 and ev["likelihood_ratio"] == 1.0


def test_satellite_eligible_returns_evidence():
    ev = c.post("/satellite/check", json={"ticket_id": "blr-0002"}).json()
    assert ev["check"] == "satellite" and ev["ticket_id"] == "blr-0002" and ev["cost"] == 3


def test_reopen_flips_status():
    assert c.post("/muni/tickets/blr-0003/reopen").json()["status"] == "reopened"
    assert c.get("/tickets/blr-0003").json()["status"] == "reopened"


def test_unknown_ticket_404():
    assert c.get("/tickets/nope").status_code == 404
