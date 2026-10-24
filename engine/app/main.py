"""Engine service (port 8001).

Serves the real tickets from the Parquet warehouse (run `python -m app.ingest all` first). With no warehouse it
falls back to the contract fixtures. GET /health says which mode is active.

Run: uvicorn app.main:app --port 8001 --reload   (from engine/)
"""
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .models import Evidence, MuniActionResult, SatelliteCheckRequest, Score, Ticket, TicketWithScore
from .store import store

app = FastAPI(title="TrueClose Engine", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _ticket(ticket_id: str) -> Ticket:
    t = store.get_ticket(ticket_id)
    if t is None:
        raise HTTPException(404, f"unknown ticket {ticket_id}")
    return t


@app.get("/health")
def health() -> dict:
    return {"service": "engine", "ok": True, "mode": store.mode}


@app.get("/cities")
def cities() -> list[dict]:
    """Per-city counts and data-quality badge inputs for the UI's city switcher."""
    return store.cities()


@app.get("/tickets", response_model=list[TicketWithScore])
def list_tickets(
    city: Optional[str] = None,
    ward: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    min_score: float = 0.0,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[TicketWithScore]:
    """Newest first. Until the Phase 3 scorer exists every real ticket carries the 0.5 baseline prior."""
    return store.list_tickets(city=city, ward=ward, category=category, status=status, min_score=min_score,
                              limit=limit, offset=offset)


@app.get("/tickets/{ticket_id}", response_model=Ticket)
def get_ticket(ticket_id: str) -> Ticket:
    return _ticket(ticket_id)


@app.get("/tickets/{ticket_id}/score", response_model=Score)
def get_score(ticket_id: str) -> Score:
    _ticket(ticket_id)
    return store.get_score(ticket_id)


@app.post("/satellite/check", response_model=Evidence)
def satellite_check(req: SatelliteCheckRequest) -> Evidence:
    """Eligibility is real (category and location precision). The change measurement is a STUB until Phase 4:
    eligible tickets return inconclusive with details.stub=true. Ineligible ones return inconclusive at cost 0."""
    _ticket(req.ticket_id)
    return store.satellite_evidence(req.ticket_id)


@app.get("/wards/stats")
def ward_stats(city: Optional[str] = None, category: Optional[str] = None,
               limit: int = Query(500, ge=1, le=5000)) -> list[dict]:
    """official_rate = share of tickets no longer open. honest_rate is null until the scorer exists."""
    return store.ward_stats(city, category)[:limit]


@app.get("/eval/results")
def eval_results() -> dict:
    return store.eval_results


@app.post("/connectors/{name}/sync")
def connector_sync(name: str) -> dict:
    """Re-run a connector (mumbai | bengaluru | pune | synthetic) and reload the store. Takes 10 to 30 seconds."""
    from .ingest import SOURCES, ingest  # imported lazily: pulls in pandas

    if name not in SOURCES:
        raise HTTPException(404, f"unknown connector {name!r}; choose from {sorted(SOURCES)}")
    src = SOURCES[name]()
    df = ingest(src)
    store.reload()
    return {"connector": name, "synced": len(df), "report": dict(src.report), "mode": store.mode,
            "note": "restart the service to switch from fixtures to the warehouse" if store.mode == "fixtures" else None}


# ---- Simulated municipal system (clearly labelled simulated in the UI) ----
@app.get("/muni/tickets", response_model=list[Ticket])
def muni_tickets(limit: int = Query(100, ge=1, le=1000)) -> list[Ticket]:
    return store.muni_tickets(limit)


@app.post("/muni/tickets/{ticket_id}/reopen", response_model=MuniActionResult)
def muni_reopen(ticket_id: str) -> MuniActionResult:
    _ticket(ticket_id)
    store.set_status(ticket_id, "reopened")
    return MuniActionResult(ticket_id=ticket_id, status="reopened", note="simulated municipal system")


@app.post("/muni/tickets/{ticket_id}/escalate", response_model=MuniActionResult)
def muni_escalate(ticket_id: str) -> MuniActionResult:
    t = _ticket(ticket_id)
    return MuniActionResult(ticket_id=ticket_id, status=t.status, note="escalated (simulated municipal system)")
