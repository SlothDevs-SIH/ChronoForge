"""Engine service (port 8001).

Serves the real tickets from the Parquet warehouse (run `python -m app.ingest all` first). With no warehouse it
falls back to the contract fixtures. GET /health says which mode is active.

Run: uvicorn app.main:app --port 8001 --reload   (from engine/)
"""
import os
import re
import threading
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import auth, errors
from .models import Evidence, MuniActionResult, SatelliteCheckRequest, Score, Ticket, TicketWithScore
from .store import store

_sync_lock = threading.Lock()


app = FastAPI(title="TrueClose Engine", version="0.2.0")
# CORS allowlist from CORS_ORIGINS (comma separated). Unset means "*", acceptable only for a local demo.
_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()] or ["*"]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-ID"])
errors.install(app)


def _ticket(ticket_id: str) -> Ticket:
    t = store.get_ticket(ticket_id)
    if t is None:
        raise HTTPException(404, f"unknown ticket {ticket_id}")
    return t


@app.get("/health")
def health() -> dict:
    return {"service": "engine", "ok": True, "mode": store.mode}


@app.get("/ready")
def ready():
    """Readiness: the store is loaded and, unless fixtures were asked for, the real warehouse is present."""
    from .store import WAREHOUSE_DIR
    files = sorted(f.name for f in WAREHOUSE_DIR.glob("tickets_*.parquet")) if WAREHOUSE_DIR.exists() else []
    fixtures_ok = os.environ.get("ENGINE_DATA_MODE") == "fixtures"
    ok = store.mode == "warehouse" or fixtures_ok
    body = {"service": "engine", "ready": ok, "store_loaded": True, "mode": store.mode, "warehouse_files": len(files),
            "reason": None if ok else "no warehouse loaded: set WAREHOUSE_URL or run the ingest"}
    return JSONResponse(body, status_code=200 if ok else 503)


@app.get("/cities")
def cities() -> list[dict]:
    """Per-city counts and data-quality badge inputs for the UI's city switcher."""
    return store.cities()


@app.get("/tickets", response_model=list[TicketWithScore], dependencies=[Depends(auth.staff)])
def list_tickets(
    city: Optional[str] = None,
    ward: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    sort: Literal["newest", "risk"] = "newest",
) -> list[TicketWithScore]:
    """sort=newest (default) or sort=risk (highest p_false_closure first). Read score.score_type before treating
    p_false_closure as a probability: only the synthetic cities are calibrated; Bengaluru and Mumbai are bounded priors."""
    return store.list_tickets(city=city, ward=ward, category=category, status=status, min_score=min_score,
                              limit=limit, offset=offset, sort=sort)


@app.get("/tickets/{ticket_id}", response_model=Ticket, dependencies=[Depends(auth.ticket_reader)])
def get_ticket(ticket_id: str) -> Ticket:
    return _ticket(ticket_id)


@app.get("/tickets/{ticket_id}/score", response_model=Score, dependencies=[Depends(auth.ticket_reader)])
def get_score(ticket_id: str) -> Score:
    _ticket(ticket_id)
    return store.get_score(ticket_id)


@app.post("/satellite/check", response_model=Evidence, dependencies=[Depends(auth.staff)])
def satellite_check(req: SatelliteCheckRequest) -> Evidence:
    """Real Sentinel-2 check. Ineligible tickets (wrong category, no exact point, no closing date) return inconclusive at
    cost 0. Eligible ones read imagery live (10 to 60 s) or from the cache; cached_only=true never reads live and answers
    instantly. details.source says "live" or "cached". Cloud, missing scenes and read errors abstain (inconclusive)."""
    _ticket(req.ticket_id)
    return store.satellite_evidence(req.ticket_id, cached_only=req.cached_only, refresh=req.refresh)


@app.get("/satellite/chip/{ticket_id}/{which}.png", dependencies=[Depends(auth.ticket_reader)])
def satellite_chip(ticket_id: str, which: Literal["before", "after"]):
    """Before/after image chip (about 400 m across, site window outlined) written by a live or cached check."""
    from .satellite import verifier
    if not re.fullmatch(r"[A-Za-z0-9_.\-]{1,80}", ticket_id):
        raise HTTPException(404, "no such chip")
    path = verifier.chip_path(ticket_id, which)
    if not path.exists():
        raise HTTPException(404, "no chip for this ticket yet: run /satellite/check first")
    return FileResponse(path, media_type="image/png")


DEMO_PHOTOS = Path(__file__).resolve().parents[2] / "demo" / "photos"


@app.get("/media/demo/{ticket_id}/{which}.jpg")
def demo_photo(ticket_id: str, which: Literal["before", "after"]):
    """The demo set's own photos (open-licence Wikimedia Commons, see demo/photos/ATTRIBUTION.md). Only files the ticket
    row points at, and only inside demo/photos/."""
    t = store.get_ticket(ticket_id)
    rel = None if t is None else (t.complaint_photo_url if which == "before" else t.closure_photo_url)
    if not rel or not rel.startswith("demo/photos/"):
        raise HTTPException(404, "no photo for this ticket")
    path = (DEMO_PHOTOS / rel[len("demo/photos/"):]).resolve()
    if DEMO_PHOTOS not in path.parents or not path.is_file():
        raise HTTPException(404, "no photo for this ticket")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/wards/stats", dependencies=[Depends(auth.staff)])
def ward_stats(city: Optional[str] = None, category: Optional[str] = None,
               limit: int = Query(500, ge=1, le=5000)) -> list[dict]:
    """official_rate = share of tickets no longer open. honest_rate is null until the scorer exists."""
    return store.ward_stats(city, category)[:limit]


@app.get("/wards/map", dependencies=[Depends(auth.staff)])
def ward_map(city: str) -> list[dict]:
    """Ward dots for the overview map: position, official rate and reopen rate (null where the city has no reopen status)."""
    return store.ward_map(city)


@app.get("/eval/results")
def eval_results() -> dict:
    return store.eval_results


@app.post("/connectors/{name}/sync", dependencies=[Depends(auth.admin_or_token)])
def connector_sync(name: str) -> dict:
    """Re-run a connector (mumbai | bengaluru | pune | synthetic) and reload the store. Takes 10 to 30 seconds."""
    from .ingest import SOURCES, ingest  # imported lazily: pulls in pandas

    if name not in SOURCES:
        raise HTTPException(404, f"unknown connector {name!r}; choose from {sorted(SOURCES)}")
    if not _sync_lock.acquire(blocking=False):   # two syncs at once would race on the same Parquet files
        raise HTTPException(409, "a sync is already running; try again in a minute")
    try:
        src = SOURCES[name]()
        df = ingest(src)
        store.reload()
    finally:
        _sync_lock.release()
    return {"connector": name, "synced": len(df), "report": dict(src.report), "mode": store.mode,
            "note": "restart the service to switch from fixtures to the warehouse" if store.mode == "fixtures" else None}


# ---- Simulated municipal system (clearly labelled simulated in the UI) ----
@app.get("/muni/tickets", response_model=list[Ticket], dependencies=[Depends(auth.service_caller)])
def muni_tickets(limit: int = Query(100, ge=1, le=1000)) -> list[Ticket]:
    return store.muni_tickets(limit)


@app.post("/muni/tickets/{ticket_id}/reopen", response_model=MuniActionResult, dependencies=[Depends(auth.service_caller)])
def muni_reopen(ticket_id: str) -> MuniActionResult:
    t = _ticket(ticket_id)
    if t.status != "closed":   # only a closed ticket can be reopened; an open or already reopened one cannot
        raise HTTPException(409, f"ticket {ticket_id} is {t.status}; only a closed ticket can be reopened")
    store.set_status(ticket_id, "reopened")
    return MuniActionResult(ticket_id=ticket_id, status="reopened", note="simulated municipal system")


@app.post("/muni/tickets/{ticket_id}/escalate", response_model=MuniActionResult, dependencies=[Depends(auth.service_caller)])
def muni_escalate(ticket_id: str) -> MuniActionResult:
    t = _ticket(ticket_id)
    return MuniActionResult(ticket_id=ticket_id, status=t.status, note="escalated (simulated municipal system)")
