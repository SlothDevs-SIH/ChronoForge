import asyncio
import os

os.environ["STEP_DELAY_S"] = "0"
os.environ["OUTCOME_DELAY_S"] = "0"

import pytest
from fastapi.testclient import TestClient

from app import fusion, main, planner
from app.audit import AuditLog


class FakeEngine:
    def __init__(self, prior=0.82, sat=False):
        self.prior, self.sat = prior, sat
        self.reopened = []

    async def get_score(self, tid):
        return {"ticket_id": tid, "p_false_closure": self.prior, "satellite_eligible": self.sat,
                "reasons": [{"feature": "time_to_close_h", "value": 0.07, "shap": 0.3}]}

    async def satellite_check(self, tid):
        return {"evidence_id": "e-sat", "ticket_id": tid, "check": "satellite", "verdict": "supports_fix",
                "likelihood_ratio": 0.3, "confidence": 0.7, "cost": 3, "details": {}, "created_at": "x"}

    async def reopen(self, tid):
        self.reopened.append(tid)
        return {"ticket_id": tid, "status": "reopened"}

    async def escalate(self, tid):
        return {"ticket_id": tid, "status": "closed"}

    async def get_ticket(self, tid):
        return {"ticket_id": tid, "status": "reopened" if tid in self.reopened else "closed"}


# ---- fusion ----
def test_fusion_matches_hand_calculation():
    # prior 0.5, LR 4 -> odds 4 -> 0.8
    assert fusion.fuse(0.5, [4.0]) == pytest.approx(0.8)
    assert fusion.fuse(0.5, [4.0, 0.25]) == pytest.approx(0.5)


def test_fusion_thresholds():
    assert fusion.verdict_state(0.75) == "likely_not_fixed"
    assert fusion.verdict_state(0.25) == "verified_fixed"
    assert fusion.verdict_state(0.5) == "cannot_tell"


# ---- audit chain ----
def test_audit_chain_detects_tampering():
    log = AuditLog()
    for i in range(3):
        log.append({"n": i})
    assert log.verify()["ok"]
    log.rows[1]["event"]["n"] = 99
    assert log.verify() == {"ok": False, "first_bad_index": 1, "length": 3}


# ---- planner ----
def run(engine):
    events = []
    out = asyncio.run(planner.run_agent("r1", "t1", engine, events.append))
    return out, events


def test_ineligible_satellite_is_skipped_for_free():
    out, events = run(FakeEngine(sat=False))
    assert any(e["tool"] == "check_satellite" and "Skipped" in e["summary"] for e in events)
    assert not any(e["tool"] == "check_satellite" and e["type"] == "tool_call" for e in events)


def test_budget_is_never_exceeded_and_verdict_present():
    out, events = run(FakeEngine(prior=0.5, sat=True))
    assert events[-1]["type"] == "verdict"
    assert all(e["budget_left"] >= 0 for e in events)
    assert out["verdict"]["requires_human"] is True


def test_score_alone_never_gives_a_verdict():
    out, events = run(FakeEngine(prior=0.99))
    assert any(e["type"] == "tool_call" and e["tool"] != "get_score" for e in events)
    assert out["verdict"]["evidence_ids"]


def test_stops_early_when_confident():
    # prior 0.9 plus the photo stub LR 8 leaves the uncertain band after one check
    out, events = run(FakeEngine(prior=0.9))
    assert out["verdict"]["state"] == "likely_not_fixed"
    assert sum(1 for e in events if e["type"] == "tool_call" and e["tool"] != "get_score") == 1


# ---- service flow ----
def test_run_then_approve_calls_municipal_reopen():
    fake = FakeEngine(prior=0.9)
    main.set_engine(fake)
    c = TestClient(main.app)
    run_id = c.post("/agent/run/t1").json()["run_id"]
    data = c.get(f"/agent/runs/{run_id}").json()
    assert data["done"] and data["verdict"]["state"] == "likely_not_fixed"
    pending = c.get("/approvals", params={"status": "pending"}).json()
    assert len(pending) == 1 and pending[0]["action"] == "reopen"
    c.post(f"/approvals/{pending[0]['approval_id']}/decide", json={"decision": "approve", "note": "ok"})
    assert fake.reopened == ["t1"]
    assert c.get("/audit/verify").json()["ok"]


def test_decide_twice_is_conflict():
    main.set_engine(FakeEngine(prior=0.9))
    c = TestClient(main.app)
    c.post("/agent/run/t2")
    aid = c.get("/approvals", params={"status": "pending"}).json()[0]["approval_id"]
    assert c.post(f"/approvals/{aid}/decide", json={"decision": "reject"}).status_code == 200
    assert c.post(f"/approvals/{aid}/decide", json={"decision": "approve"}).status_code == 409
