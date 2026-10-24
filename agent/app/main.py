"""Agent service (port 8002). Run: uvicorn app.main:app --port 8002"""
import asyncio
import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from . import agent, approvals, audit, config, tools
from .db import get_conn
from .models import DecideRequest, PhotoRequest
from .photo import PhotoIndex, verify_photo

app = FastAPI(title="TrueClose Agent service")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"ok": True, "service": "agent", "stubs": config.USE_STUBS}


@app.post("/evidence/photo")
def evidence_photo(req: PhotoRequest):
    ticket = tools._get_ticket(req.ticket_id)
    try:
        return verify_photo(req.ticket_id, req.closure_photo_url, ticket, PhotoIndex())
    except Exception as exc:
        raise HTTPException(422, f"could not read photo: {exc}")


@app.post("/agent/run/{ticket_id}")
def run_ticket(ticket_id: str):
    run_id = agent.start_run(ticket_id)
    agent.run_in_background(run_id)
    return {"run_id": run_id}


@app.get("/agent/stream/{run_id}")
async def stream(run_id: str):
    run = agent.RUNS.get(run_id)
    if run is None:
        raise HTTPException(404, "unknown run")

    async def gen():
        sent = 0
        while True:
            while sent < len(run.events):
                yield {"event": "trace", "data": run.events[sent].model_dump_json()}
                sent += 1
            if run.status != "running" and sent >= len(run.events):
                yield {"event": "end", "data": json.dumps({"status": run.status})}
                return
            await asyncio.sleep(0.1)

    return EventSourceResponse(gen())


@app.get("/agent/runs/{run_id}")
def get_run(run_id: str):
    run = agent.RUNS.get(run_id)
    if run is not None:
        return {"run_id": run_id, "ticket_id": run.ticket_id, "status": run.status,
                "trace": [e.model_dump() for e in run.events], "verdict": run.verdict}
    r = get_conn().execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if r is None:
        raise HTTPException(404, "unknown run")
    return {"run_id": run_id, "ticket_id": r["ticket_id"], "status": r["status"],
            "trace": json.loads(r["trace"]), "verdict": json.loads(r["verdict"]) if r["verdict"] else None}


@app.get("/approvals")
def list_approvals(status: str | None = "pending"):
    return approvals.list_approvals(status)


@app.post("/approvals/{approval_id}/decide")
def decide(approval_id: str, req: DecideRequest):
    try:
        return approvals.decide(approval_id, req.decision, req.note)
    except KeyError:
        raise HTTPException(404, "unknown approval")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/outcomes")
def outcomes():
    return approvals.outcomes()


@app.get("/audit")
def get_audit(limit: int = 500):
    return audit.entries(limit)


@app.get("/audit/verify")
def verify_audit():
    return audit.verify()
