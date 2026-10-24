"""Pydantic models. These mirror the JSON contract in contract/ (see contract/README.md)."""
from typing import Any, Literal, Optional

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
    lat: float
    lng: float
    h3: str
    ward: str
    created_at: str
    closed_at: Optional[str] = None
    closed_by_hash: Optional[str] = None
    status: Literal["open", "closed", "reopened"]
    closure_note: Optional[str] = None
    closure_photo_url: Optional[str] = None


class Reason(BaseModel):
    feature: str
    value: float
    shap: float


class Score(BaseModel):
    ticket_id: str
    p_false_closure: float
    model_version: str
    reasons: list[Reason]
    eligible_checks: list[str]
    satellite_eligible: bool


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


class MuniActionResult(BaseModel):
    ticket_id: str
    status: Literal["open", "closed", "reopened"]
    note: Optional[str] = None
