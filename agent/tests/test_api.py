import time

from fastapi.testclient import TestClient

from app.main import app
from tests.test_core import ticket_with

client = TestClient(app)


def wait_done(run_id, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        r = client.get(f"/agent/runs/{run_id}").json()
        if r["status"] != "running":
            return r
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_run_returns_fast_and_trace_and_verdict_are_available():
    t0 = time.time()
    run_id = client.post(f"/agent/run/{ticket_with(True)}").json()["run_id"]
    assert time.time() - t0 < 0.2
    out = wait_done(run_id)
    assert out["verdict"]["state"] == "likely_not_fixed"
    assert out["trace"][-1]["type"] == "approval_needed"


def test_sse_stream_emits_trace_events_then_end():
    run_id = client.post(f"/agent/run/{ticket_with(False, satellite=True)}").json()["run_id"]
    wait_done(run_id)
    body = client.get(f"/agent/stream/{run_id}").text
    assert "event: trace" in body and '"type":"verdict"' in body and "event: end" in body


def test_approval_queue_and_audit_verify():
    run_id = client.post(f"/agent/run/{ticket_with(True)}").json()["run_id"]
    wait_done(run_id)
    pending = client.get("/approvals").json()
    assert len(pending) == 1
    done = client.post(f"/approvals/{pending[0]['approval_id']}/decide", json={"decision": "reject", "note": "n"})
    assert done.json()["status"] == "rejected"
    assert client.post(f"/approvals/{pending[0]['approval_id']}/decide", json={"decision": "approve"}).status_code == 409
    assert client.get("/audit/verify").json()["ok"] is True


def test_unknown_run_is_404():
    assert client.get("/agent/runs/nope").status_code == 404
