"""Interface checklist (backend_ayush.md section 12): what Ishan's UI and the contract rely on."""
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from tests.test_core import ticket_with

CONTRACT = Path(__file__).resolve().parents[2] / "contract"
TRACE_KEYS = set(json.loads((CONTRACT / "trace_events.json").read_text())[0])
VERDICT_KEYS = set(json.loads((CONTRACT / "verdict.json").read_text()).keys()) if (CONTRACT / "verdict.json").exists() else set()
client = TestClient(app)


def run_to_completion(ticket_id):
    t0 = time.perf_counter()
    r = client.post(f"/agent/run/{ticket_id}")
    elapsed = time.perf_counter() - t0
    run_id = r.json()["run_id"]
    for _ in range(100):   # the run is a background thread; wait so it never outlives the test's database
        body = client.get(f"/agent/runs/{run_id}").json()
        if body["status"] != "running":
            return run_id, body, elapsed
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_run_returns_within_200ms_and_works_in_background():
    run_id, body, elapsed = run_to_completion(ticket_with(True))
    assert elapsed < 0.2 and body["status"] == "done"


def test_sse_events_match_the_contract_trace_shape():
    run_id, _, _ = run_to_completion(ticket_with(True))
    seen = []
    with client.stream("GET", f"/agent/stream/{run_id}") as resp:
        for line in resp.iter_lines():
            if line.startswith("data: ") and line != "data: ":
                try:
                    payload = json.loads(line[6:])
                except ValueError:
                    continue
                if "step" in payload:
                    seen.append(payload)
    assert seen and all(set(e) == TRACE_KEYS for e in seen)
    assert {e["type"] for e in seen} <= {"thought", "tool_call", "tool_result", "verdict", "approval_needed"}
    assert [e["step"] for e in seen] == sorted(e["step"] for e in seen)


def test_approval_carries_full_verdict_snapshot_and_audit_verifies():
    run_to_completion(ticket_with(True))
    pending = client.get("/approvals").json()
    assert len(pending) == 1
    snap = pending[0]["verdict_snapshot"]
    assert {"ticket_id", "state", "prior", "posterior", "evidence_ids", "recommended_action",
            "requires_human", "explanation"} <= set(snap)
    assert VERDICT_KEYS <= set(snap)
    done = client.post(f"/approvals/{pending[0]['approval_id']}/decide", json={"decision": "reject", "note": "x"})
    assert done.json()["status"] == "rejected"
    assert client.get("/audit/verify").json()["ok"] is True


def test_contract_endpoint_aliases_exist():
    paths = {r.path for r in app.routes}
    for p in ("/agent/run/{ticket_id}", "/agent/stream/{run_id}", "/agent/runs/{run_id}", "/evidence/photo",
              "/citizen/send", "/telegram/webhook", "/whatsapp/webhook", "/approvals",
              "/approvals/{approval_id}/decide", "/audit", "/audit/verify"):
        assert p in paths, p
