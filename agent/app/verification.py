"""Persisted verification runs (contract/AUTH_AND_DEPLOY.md).

One record per run, written when the run ends. It keeps three things apart:
  closure_claimed       what the city says about the ticket (from the Engine; "unknown" if we could not read it)
  verification_verdict  what the engine concluded from the evidence
  review_state          what a person has decided (computed live from the approvals table)

Nothing here changes a ratio, prior, threshold or verdict: it only describes what the run already did. A check that did
not run or could not run is `performed: false` with a reason and is never counted as evidence.
"""
import json

from fastapi import APIRouter, Depends

from . import config
from .auth import Principal, authorize_ticket, authenticated, valid_ticket_id
from .db import get_conn, lock
from .models import Evidence, Verdict, now_iso

router = APIRouter()
CHECKS = ("photo", "satellite", "citizen", "human")


def _ticket_info(ticket_id: str) -> dict | None:
    """The city's own record of the ticket, or None. Never invented: stub mode and an unreachable Engine give None."""
    if config.USE_STUBS:
        return None
    from . import tools
    return tools._get_ticket(ticket_id)


def _skip_reason(ev: Evidence) -> str | None:
    """A check is skipped when it gave no information and said why (not applicable, no photo, no contact, failed)."""
    if ev.verdict == "inconclusive" and ev.likelihood_ratio == 1.0:
        reason = ev.details.get("reason")
        if reason:
            return str(reason)
        if ev.details.get("pending"):
            return "awaiting reply"
        if ev.check == "satellite":   # unavailable imagery (cloud, no scene, read error) is skipped, never evidence
            return str(ev.details.get("abstain_reason") or "no usable imagery")
    return None


def _check_rows(evidence: list[Evidence], satellite_eligible: bool | None) -> list[dict]:
    latest: dict[str, Evidence] = {}
    for ev in evidence:
        latest[ev.check] = ev            # repeated checks of one type: the latest counts (same rule as fusion)
    rows = []
    for check in CHECKS:
        ev = latest.get(check)
        if ev is None:
            reason = "not applicable to this ticket" if (check == "satellite" and satellite_eligible is False) else "not run"
            rows.append({"check": check, "performed": False, "skipped_reason": reason, "verdict": None,
                         "likelihood_ratio": None, "cost": 0})
            continue
        why = _skip_reason(ev)
        rows.append({"check": check, "performed": why is None, "skipped_reason": why,
                     "verdict": None if why else ev.verdict,
                     "likelihood_ratio": None if why else ev.likelihood_ratio,
                     "cost": ev.cost})
    return rows


def build_record(run, verdict: Verdict, prior: float, source: str, score) -> dict:
    ticket = _ticket_info(run.ticket_id) or {}
    checks = _check_rows(run.evidence, getattr(score, "satellite_eligible", None))
    performed = [c for c in checks if c["performed"]]
    return {
        "run_id": run.run_id, "ticket_id": run.ticket_id, "created_at": now_iso(), "status": "done",
        "config_version": config.CONFIG_VERSION, "calibrated": config.CALIBRATED,
        "closure_claimed": ticket.get("status") or "unknown",
        "verification_verdict": verdict.state if performed else "not_performed",
        "prior": verdict.prior, "posterior": verdict.posterior,
        "checks": checks,
        "provenance": {"data_quality": ticket.get("data_quality"), "score_type": getattr(score, "score_type", None),
                       "city": ticket.get("city"), "prior_source": source},
        "note": config.CALIBRATION_NOTE,
    }


def _store(run_id: str, ticket_id: str, record: dict) -> None:
    with lock():
        get_conn().execute("DELETE FROM verification_runs WHERE run_id=?", (run_id,))
        get_conn().execute("INSERT INTO verification_runs (run_id, ticket_id, status, record, created_at) VALUES (?,?,?,?,?)",
                           (run_id, ticket_id, record["status"], json.dumps(record), record["created_at"]))
        get_conn().commit()


def record_run(run, verdict: Verdict, prior: float, source: str, score) -> dict:
    rec = build_record(run, verdict, prior, source, score)
    _store(run.run_id, run.ticket_id, rec)
    return rec


def record_pending(run, reason: str) -> dict:
    """The run could not finish (for example the Engine is down). Stored as pending with the reason; no scores."""
    rec = {"run_id": run.run_id, "ticket_id": run.ticket_id, "created_at": now_iso(), "status": "pending",
           "config_version": config.CONFIG_VERSION, "calibrated": config.CALIBRATED,
           "closure_claimed": "unknown", "verification_verdict": "not_performed",
           "prior": None, "posterior": None, "checks": [], "provenance": {},
           "pending_reason": reason, "note": config.CALIBRATION_NOTE}
    _store(run.run_id, run.ticket_id, rec)
    return rec


def _review_state(run_id: str) -> str:
    row = get_conn().execute("SELECT status FROM approvals WHERE run_id=? ORDER BY created_at DESC", (run_id,)).fetchone()
    return row["status"] if row else "none"


def _load(row) -> dict:
    rec = json.loads(row["record"])
    rec["review_state"] = _review_state(rec["run_id"])
    return rec


def _pending_stub(ticket_id: str) -> dict:
    return {"run_id": None, "ticket_id": ticket_id, "status": "pending", "config_version": config.CONFIG_VERSION,
            "calibrated": config.CALIBRATED, "closure_claimed": "unknown", "verification_verdict": "not_performed",
            "review_state": "none", "prior": None, "posterior": None, "checks": [], "provenance": {},
            "pending_reason": "No verification has been run for this ticket yet.", "note": config.CALIBRATION_NOTE}


@router.get("/verification/{ticket_id}", tags=["verification"])
def list_verifications(ticket_id: str, limit: int = 20, p: Principal = Depends(authenticated)):
    """Newest first. Staff see any ticket; a citizen sees only a ticket linked to them."""
    valid_ticket_id(ticket_id)
    authorize_ticket(p, ticket_id)
    rows = get_conn().execute("SELECT * FROM verification_runs WHERE ticket_id=? ORDER BY created_at DESC LIMIT ?",
                              (ticket_id, max(1, min(limit, 100)))).fetchall()
    return [_load(r) for r in rows]


@router.get("/verification/{ticket_id}/latest", tags=["verification"])
def latest_verification(ticket_id: str, p: Principal = Depends(authenticated)):
    valid_ticket_id(ticket_id)
    authorize_ticket(p, ticket_id)
    row = get_conn().execute("SELECT * FROM verification_runs WHERE ticket_id=? ORDER BY created_at DESC LIMIT 1",
                             (ticket_id,)).fetchone()
    return _load(row) if row else _pending_stub(ticket_id)
