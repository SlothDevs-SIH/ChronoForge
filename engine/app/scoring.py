"""Scorer entry point. PHASE 3 replaces baseline_score with the LightGBM + logistic ensemble.

Until then every real ticket gets an uninformative prior of 0.5, labelled model_version="baseline-no-model", with no
reasons. A 0.5 prior adds nothing in the agent's log-odds fusion, so verdicts come from evidence only. This is
deliberate: we do not invent a number we have not measured.
"""
from .eligibility import eligible_checks, satellite_eligibility
from .models import Score

BASELINE_VERSION = "baseline-no-model"


def baseline_score(ticket_id: str, category: str, location_precision: str | None) -> Score:
    return Score(
        ticket_id=ticket_id, p_false_closure=0.5, model_version=BASELINE_VERSION, reasons=[],
        eligible_checks=eligible_checks(category, location_precision),
        satellite_eligible=satellite_eligibility(category, location_precision)[0],
    )
