"""Turns a stored score row into the Score contract.

Tickets with a trained or rule-based score (see app/scorer/train.py) carry it. Everything else (open tickets, Bengaluru
tickets from before the reopen mechanism existed) gets the neutral 0.5, labelled model_version="baseline-no-model". A 0.5
prior adds nothing in the agent's log-odds fusion, so verdicts then come from evidence only. We never invent a number.
"""
from .eligibility import eligible_checks, satellite_eligibility
from .models import Score

BASELINE_VERSION = "baseline-no-model"


def baseline_score(ticket_id: str, category: str, location_precision: str | None, text: str | None = None) -> Score:
    ok, why = satellite_eligibility(category, location_precision, text)
    return Score(
        ticket_id=ticket_id, p_false_closure=0.5, model_version=BASELINE_VERSION, reasons=[],
        eligible_checks=eligible_checks(category, location_precision, text),
        satellite_eligible=ok, satellite_reason=why,
    )


def from_row(t, row: dict) -> Score:
    """row has the score columns of view `vs`: _p, _score_type, _pct, _mv, _flags (all None when unscored)."""
    if row.get("_p") is None:
        return baseline_score(t.ticket_id, t.category, t.location_precision, t.text)
    pct = row.get("_pct")
    ok, why = satellite_eligibility(t.category, t.location_precision, t.text)
    return Score(
        ticket_id=t.ticket_id, p_false_closure=float(row["_p"]), model_version=row["_mv"], reasons=[],
        eligible_checks=eligible_checks(t.category, t.location_precision, t.text),
        satellite_eligible=ok, satellite_reason=why,
        score_type=row["_score_type"], risk_percentile=None if pct is None or pct != pct else round(float(pct), 4),
        flags=[f for f in (row.get("_flags") or "").split(",") if f],
    )
