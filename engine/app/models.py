"""Pydantic models. These mirror the JSON contract in contract/ (see contract/README.md)."""
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel

City = Literal["bengaluru", "pune", "mumbai", "synthetic"]
Category = Literal["pothole", "garbage", "streetlight", "drain", "water_leak", "other"]


class Ticket(BaseModel):
    ticket_id: str
    city: City
    data_quality: Literal["real", "partial", "synthetic"]
    source: str
    category: Category
    text: str
    lang: str
    # Bengaluru has no exact point: lat/lng are a ward centroid (location_precision="ward_centroid") or None, and h3 is None.
    lat: Optional[float] = None
    lng: Optional[float] = None
    h3: Optional[str] = None
    location_precision: Optional[Literal["exact", "generated", "ward_centroid", "none"]] = None
    ward: str
    created_at: str
    closed_at: Optional[str] = None
    closed_by_hash: Optional[str] = None
    status: Literal["open", "closed", "reopened"]
    closure_note: Optional[str] = None
    closure_photo_url: Optional[str] = None


class Reason(BaseModel):
    feature: str
    value: Union[float, str, None] = None   # categorical features carry their text value
    shap: Optional[float] = None            # log-odds contribution (TreeSHAP, or ln(odds ratio) for a rule flag)


class Score(BaseModel):
    ticket_id: str
    p_false_closure: float
    model_version: str
    reasons: list[Reason]
    eligible_checks: list[str]
    satellite_eligible: bool
    satellite_reason: Optional[str] = None   # why the satellite check applies or is "not applicable"; shown on the website
    # How to read p_false_closure:
    #   calibrated_probability  synthetic cities only (ground truth by construction)
    #   risk_rank_prior         Bengaluru: a rank mapped into [0.30, 0.70]; NOT a probability
    #   rule_flags              Mumbai: 0.5, or a measured-odds-ratio nudge when a flag fires; NOT a probability
    #   baseline                no model applies (open tickets, older Bengaluru tickets): the neutral 0.5
    score_type: Literal["baseline", "risk_rank_prior", "rule_flags", "calibrated_probability"] = "baseline"
    risk_percentile: Optional[float] = None
    flags: list[str] = []


class Evidence(BaseModel):
    evidence_id: str
    ticket_id: str
    check: Literal["photo", "satellite", "citizen", "human"]
    verdict: Literal["supports_fix", "contradicts_fix", "inconclusive"]
    likelihood_ratio: float
    confidence: float
    cost: int
    details: dict[str, Any]
    created_at: str


class TicketWithScore(BaseModel):
    ticket: Ticket
    score: Score


class SatelliteCheckRequest(BaseModel):
    ticket_id: str
    cached_only: bool = False   # never read live imagery; answer from the cache or abstain (instant)
    refresh: bool = False       # ignore the cache and measure again


class MuniActionResult(BaseModel):
    ticket_id: str
    status: Literal["open", "closed", "reopened"]
    note: Optional[str] = None
