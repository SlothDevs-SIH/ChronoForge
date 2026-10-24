"""Pydantic models that mirror the JSON contract in 00_contract_and_timeline.md."""
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4
from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


Check = Literal["photo", "satellite", "citizen", "human"]
EvVerdict = Literal["supports_fix", "contradicts_fix", "inconclusive"]


class Evidence(BaseModel):
    evidence_id: str = Field(default_factory=lambda: str(uuid4()))
    ticket_id: str
    check: Check
    verdict: EvVerdict
    likelihood_ratio: float = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    cost: int = 0
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)


class Score(BaseModel):
    ticket_id: str
    p_false_closure: float = Field(ge=0, le=1)
    model_version: str = "unknown"
    reasons: list[dict[str, Any]] = Field(default_factory=list)
    eligible_checks: list[str] = Field(default_factory=list)
    satellite_eligible: bool = False


class Verdict(BaseModel):
    ticket_id: str
    state: Literal["verified_fixed", "likely_not_fixed", "cannot_tell"]
    prior: float
    posterior: float
    evidence_ids: list[str]
    recommended_action: Literal["none", "ask_citizen", "reopen", "escalate", "human_spot_check"]
    requires_human: bool
    explanation: str


class TraceEvent(BaseModel):
    run_id: str
    step: int
    type: Literal["thought", "tool_call", "tool_result", "verdict", "approval_needed"]
    tool: str | None = None
    summary: str
    cost_spent: int
    budget_left: int
    ts: str = Field(default_factory=now_iso)


class PhotoRequest(BaseModel):
    ticket_id: str
    closure_photo_url: str
    citizen_photo_url: str | None = None


class DecideRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: str = ""
