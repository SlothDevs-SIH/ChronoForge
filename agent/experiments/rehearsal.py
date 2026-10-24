"""Offline-mode rehearsal against a running Engine. Run from agent/ with the Engine up on ENGINE_URL:

    AGENT_USE_STUBS=0 .venv/Scripts/python -m experiments.rehearsal

Cuts the LLM off (bad provider list), runs every closed ticket the Engine serves, approves the first reopen,
and checks the audit chain. Anything unexpected is printed as a FAIL line. This is the "demo with Wi-Fi off"
dry run: only the Engine (local) is needed.
"""
import os
import sys

os.environ.setdefault("AGENT_DB", ":memory:")
os.environ["PHOTO_INDEX"] = os.path.join(os.environ.get("TEMP", "/tmp"), "rehearsal_photo_index.json")
if os.path.exists(os.environ["PHOTO_INDEX"]):
    os.remove(os.environ["PHOTO_INDEX"])      # fresh index each rehearsal
os.environ["LLM_PROVIDERS"] = ""          # no LLM: planner must fall back, nothing may need the internet
os.environ["STEP_DELAY"] = "0"
os.environ["OUTCOME_CHECK_DELAY"] = "0"

import httpx  # noqa: E402

from app import agent, approvals, audit, config  # noqa: E402

fails = 0


def check(ok: bool, msg: str):
    global fails
    print(("ok   " if ok else "FAIL ") + msg)
    fails += 0 if ok else 1


def main():
    config.USE_STUBS = False
    try:
        rows = httpx.get(f"{config.ENGINE_URL}/tickets", params={"status": "closed", "limit": 20}, timeout=5).json()
    except Exception as exc:
        raise SystemExit(f"Engine not reachable at {config.ENGINE_URL}: {exc}")
    check(len(rows) > 0, f"engine serves {len(rows)} closed tickets")
    for row in rows:
        t = row["ticket"]
        rid = agent.start_run(t["ticket_id"])
        try:
            v = agent.execute(rid, delay=0)
        except Exception as exc:
            check(False, f"{t['ticket_id']}: run crashed with {type(exc).__name__}: {exc}")
            continue
        run = agent.RUNS[rid]
        conclusive = any(e.verdict != "inconclusive" for e in run.evidence)
        check(not (v.state != "cannot_tell" and not conclusive),
              f"{t['ticket_id']} ({t['category']}): {v.state} {v.prior:.2f}->{v.posterior:.2f}, "
              f"cost {run.cost_spent}, checks {[e.check for e in run.evidence]}")
    pending = approvals.list_approvals("pending")
    if pending:
        out = approvals.decide(pending[0]["approval_id"], "approve", "rehearsal")
        check(out["status"] == "approved", f"approval decided; engine result: {out['engine_result']}")
    check(audit.verify()["ok"], "audit chain verifies")
    print("FAILED" if fails else "REHEARSAL PASSED", fails)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
