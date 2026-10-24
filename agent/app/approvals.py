"""Module 4: approvals and actions. propose_action only ever creates a pending row; nothing is
reopened or escalated without a human decision."""
import json
import threading
from uuid import uuid4

import httpx

from . import audit, config, events
from .db import get_conn, lock
from .models import Verdict, now_iso

ACTIONS = {"reopen", "escalate"}


def propose_action(ticket_id: str, run_id: str | None, action: str, verdict: Verdict) -> dict:
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action}")
    with lock():
        existing = get_conn().execute(
            "SELECT approval_id FROM approvals WHERE ticket_id=? AND action=? AND status='pending'",
            (ticket_id, action)).fetchone()
        if existing:   # a re-run (for example after a citizen reply) refreshes the open item instead of duplicating it
            get_conn().execute("UPDATE approvals SET verdict_snapshot=?, run_id=? WHERE approval_id=?",
                               (verdict.model_dump_json(), run_id, existing["approval_id"]))
            get_conn().commit()
            audit.append("approval_refreshed", {"approval_id": existing["approval_id"], "ticket_id": ticket_id,
                                                "action": action})
            return get(existing["approval_id"])
    approval_id = str(uuid4())
    with lock():
        get_conn().execute(
            "INSERT INTO approvals (approval_id, ticket_id, run_id, action, verdict_snapshot, status, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (approval_id, ticket_id, run_id, action, verdict.model_dump_json(), "pending", now_iso()))
        get_conn().commit()
    audit.append("approval_proposed", {"approval_id": approval_id, "ticket_id": ticket_id, "action": action})
    return get(approval_id)


def _row(r) -> dict:
    return {"approval_id": r["approval_id"], "ticket_id": r["ticket_id"], "run_id": r["run_id"],
            "action": r["action"], "verdict_snapshot": json.loads(r["verdict_snapshot"]),
            "status": r["status"], "note": r["note"],
            "engine_result": json.loads(r["engine_result"]) if r["engine_result"] else None,
            "created_at": r["created_at"], "decided_at": r["decided_at"],
            "actor": r["actor"], "actor_email": r["actor_email"]}


def get(approval_id: str) -> dict | None:
    r = get_conn().execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
    return _row(r) if r else None


def list_approvals(status: str | None = "pending") -> list[dict]:
    q, args = "SELECT * FROM approvals", ()
    if status:
        q, args = q + " WHERE status=?", (status,)
    return [_row(r) for r in get_conn().execute(q + " ORDER BY created_at", args).fetchall()]


def _call_engine(action: str, ticket_id: str) -> dict:
    try:
        headers = {"X-Service-Token": config.ENGINE_SERVICE_TOKEN} if config.ENGINE_SERVICE_TOKEN else {}
        r = httpx.post(f"{config.ENGINE_URL}/muni/tickets/{ticket_id}/{action}", timeout=5, headers=headers)
        r.raise_for_status()
        return {"ok": True, "response": r.json()}
    except Exception as exc:
        return {"ok": False, "error": f"engine call failed: {exc}"}


def decide(approval_id: str, decision: str, note: str = "", actor: dict | None = None) -> dict:
    """actor = {"user_id", "email"} of the person deciding; recorded on the row and in the audit chain."""
    actor = actor or {}
    a = get(approval_id)
    if a is None:
        raise KeyError(approval_id)
    if a["status"] != "pending":
        raise ValueError(f"approval already {a['status']}")
    engine_result = None
    if decision == "approve":
        engine_result = _call_engine(a["action"], a["ticket_id"])
    status = "approved" if decision == "approve" else "rejected"
    with lock():
        get_conn().execute("UPDATE approvals SET status=?, note=?, engine_result=?, decided_at=?, actor=?, actor_email=? "
                           "WHERE approval_id=?",
                           (status, note, json.dumps(engine_result) if engine_result else None, now_iso(),
                            actor.get("user_id"), actor.get("email"), approval_id))
        get_conn().commit()
    audit.append("approval_decided", {"approval_id": approval_id, "ticket_id": a["ticket_id"],
                                      "decision": decision, "note": note,
                                      "actor": actor.get("user_id"), "actor_email": actor.get("email")})
    if decision == "reject":
        events.record(a["ticket_id"], f"{a['action']}_rejected",
                      f"An administrator decided not to {a['action']}." + (f" Note: {note}" if note else ""), "staff")
    elif engine_result and not engine_result.get("ok"):
        events.record(a["ticket_id"], "action_failed",
                      f"{a['action']} was approved but the city system did not act. It can be retried.", "staff")
    if decision == "approve":
        _record_prediction(a)
        if engine_result and not engine_result.get("ok"):
            # the human approved but the municipal system did not act: say so, and start no outcome clock
            audit.append("action_failed", {"approval_id": approval_id, "ticket_id": a["ticket_id"],
                                           "error": engine_result.get("error", "")[:200]})
        elif a["action"] == "reopen":
            _announce_reopen(a["ticket_id"])
        if not (engine_result and not engine_result.get("ok")) and config.OUTCOME_CHECK_DELAY > 0:
            threading.Timer(config.OUTCOME_CHECK_DELAY, run_outcome_check, args=(approval_id,)).start()
    return get(approval_id)


def _announce_reopen(ticket_id: str) -> None:
    """Only after the city system really reopened it: record it and tell the citizen."""
    events.record(ticket_id, "reopened", "An administrator reviewed the evidence and the request was reopened.")
    try:
        from . import cases
        cases.notify(ticket_id, cases.REOPENED)
    except Exception:
        pass


def retry(approval_id: str) -> dict:
    """An approved reopen whose city call failed: try the city system again. Never acts on a rejected or pending one."""
    a = get(approval_id)
    if a is None:
        raise KeyError(approval_id)
    if a["status"] != "approved" or (a["engine_result"] or {}).get("ok", True):
        raise ValueError("nothing to retry: this approval did not fail")
    result = _call_engine(a["action"], a["ticket_id"])
    with lock():
        get_conn().execute("UPDATE approvals SET engine_result=? WHERE approval_id=?", (json.dumps(result), approval_id))
        get_conn().commit()
    audit.append("approval_retried", {"approval_id": approval_id, "ticket_id": a["ticket_id"], "ok": result["ok"]})
    if result["ok"] and a["action"] == "reopen":
        _announce_reopen(a["ticket_id"])
    return get(approval_id)


def _record_prediction(a: dict) -> None:
    with lock():
        get_conn().execute("INSERT INTO outcomes (approval_id, ticket_id, predicted, created_at) VALUES (?,?,?,?)",
                           (a["approval_id"], a["ticket_id"], a["verdict_snapshot"]["state"], now_iso()))
        get_conn().commit()


def run_outcome_check(approval_id: str) -> dict:
    """Outcome verification: re-run the agent on the ticket and record predicted vs observed."""
    from . import agent  # local import: agent imports this module
    a = get(approval_id)
    run_id = agent.start_run(a["ticket_id"])
    verdict = agent.execute(run_id, delay=0)
    observed = {"rerun_state": verdict.state, "rerun_posterior": verdict.posterior, "run_id": run_id}
    with lock():
        get_conn().execute("UPDATE outcomes SET observed=? WHERE approval_id=?", (json.dumps(observed), approval_id))
        get_conn().commit()
    audit.append("outcome_check", {"approval_id": approval_id, "ticket_id": a["ticket_id"], **observed})
    return observed


def outcomes() -> list[dict]:
    return [dict(r) for r in get_conn().execute("SELECT * FROM outcomes ORDER BY outcome_id").fetchall()]
