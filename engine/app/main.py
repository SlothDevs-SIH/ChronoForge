"""Engine service (port 8001). Serves contract fixtures until real modules replace them.

Run: uvicorn app.main:app --port 8001 --reload   (from engine/)
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .models import Evidence, MuniActionResult, SatelliteCheckRequest, Score, Ticket, TicketWithScore
from .store import store

app = FastAPI(title="TrueClose Engine", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ticket(ticket_id: str) -> Ticket:
    t = store.tickets.get(ticket_id)
    if t is None:
        raise HTTPException(404, f"unknown ticket {ticket_id}")
    return t


@app.get("/health")
def health() -> dict:
    return {"service": "engine", "ok": True, "mode": "fixtures"}


@app.get("/tickets", response_model=list[TicketWithScore])
def list_tickets(
    city: Optional[str] = None,
    ward: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    min_score: float = 0.0,
    limit: int = Query(100, le=1000),
) -> list[TicketWithScore]:
    out = []
    for t in store.tickets.values():
        s = store.scores[t.ticket_id]
        if city and t.city != city:
            continue
        if ward and t.ward != ward:
            continue
        if category and t.category != category:
            continue
        if status and t.status != status:
            continue
        if s.p_false_closure < min_score:
            continue
        out.append(TicketWithScore(ticket=t, score=s))
    out.sort(key=lambda x: x.score.p_false_closure, reverse=True)
    return out[:limit]


@app.get("/tickets/{ticket_id}", response_model=Ticket)
def get_ticket(ticket_id: str) -> Ticket:
    return _ticket(ticket_id)


@app.get("/tickets/{ticket_id}/score", response_model=Score)
def get_score(ticket_id: str) -> Score:
    _ticket(ticket_id)
    return store.scores[ticket_id]


@app.post("/satellite/check", response_model=Evidence)
def satellite_check(req: SatelliteCheckRequest) -> Evidence:
    """STUB. SOHAM: replace with the STAC read + control z-score + GEOAI-04 wrapper.
    Ineligible categories must return inconclusive with cost 0 (this is a feature, not a failure)."""
    _ticket(req.ticket_id)
    score = store.scores[req.ticket_id]
    key = "satellite" if score.satellite_eligible else "satellite_ineligible"
    ev = dict(store.evidence_templates[key])
    ev.update(ticket_id=req.ticket_id, evidence_id=str(uuid.uuid4()), created_at=_now())
    return Evidence(**ev)


@app.get("/wards/stats")
def ward_stats(city: Optional[str] = None) -> list[dict]:
    return [w for w in store.ward_stats if not city or w["city"] == city]


@app.get("/eval/results")
def eval_results() -> dict:
    return store.eval_results


@app.post("/connectors/{name}/sync")
def connector_sync(name: str) -> dict:
    """STUB. SOHAM: ingest bbmp_csv / pune / mumbai / synthetic through ComplaintSource adapters."""
    return {"connector": name, "synced": 0, "mode": "stub"}


# ---- Simulated municipal system (clearly labelled simulated in the UI) ----
@app.get("/muni/tickets", response_model=list[Ticket])
def muni_tickets() -> list[Ticket]:
    return list(store.tickets.values())


@app.post("/muni/tickets/{ticket_id}/reopen", response_model=MuniActionResult)
def muni_reopen(ticket_id: str) -> MuniActionResult:
    t = _ticket(ticket_id)
    t.status = "reopened"
    return MuniActionResult(ticket_id=ticket_id, status=t.status, note="simulated municipal system")


@app.post("/muni/tickets/{ticket_id}/escalate", response_model=MuniActionResult)
def muni_escalate(ticket_id: str) -> MuniActionResult:
    t = _ticket(ticket_id)
    return MuniActionResult(ticket_id=ticket_id, status=t.status, note="escalated (simulated municipal system)")
