"""Agent service (port 8002).

Run: uvicorn app.main:app --port 8002 --reload   (from agent/)
All state is in memory for the skeleton. AYUSH: move runs/approvals to SQLite (SQL files go in agent/sql/).
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import config, planner, tools
from .audit import AuditLog

app = FastAPI(title="TrueClose Agent", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

audit = AuditLog()
runs: dict[str, dict[str, Any]] = {}
approvals: dict[str, dict[str, Any]] = {}
_engine: Optional[tools.Engine] = None


def get_engine() -> tools.Engine:
    global _engine
    if _engine is None:
        _engine = tools.HttpEngine()
    return _engine


def set_engine(engine: tools.Engine) -> None:
    """Tests inject a fake engine here."""
    global _engine
    _engine = engine


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@app.get("/health")
def health() -> dict:
    return {"service": "agent", "ok": True, "llm": config.USE_LLM, "providers": config.LLM_PROVIDERS}


# ---------------- agent runs ----------------
async def _execute(run_id: str, ticket_id: str) -> None:
    run = runs[run_id]

    def on_event(ev: dict[str, Any]) -> None:
        ev["ts"] = _now()
        run["events"].append(ev)
        audit.append({"kind": "trace", **ev})

    try:
        audit.append({"kind": "run_started", "run_id": run_id, "ticket_id": ticket_id})
        result = await planner.run_agent(run_id, ticket_id, get_engine(), on_event)
        run.update(result)
        v = result["verdict"]
        if v["recommended_action"] in ("reopen", "human_spot_check"):
            approval_id = str(uuid.uuid4())
            action = "reopen" if v["recommended_action"] == "reopen" else "escalate"
            approvals[approval_id] = {"approval_id": approval_id, "ticket_id": ticket_id, "action": action,
                                      "verdict_snapshot": v, "status": "pending", "note": None}
            audit.append({"kind": "approval_proposed", "approval_id": approval_id, "action": action})
            last = run["events"][-1]
            on_event({"run_id": run_id, "step": last["step"] + 1, "type": "approval_needed", "tool": "propose_action",
                      "summary": f"{action} proposed; waiting for human approval",
                      "cost_spent": last["cost_spent"], "budget_left": last["budget_left"]})
    except Exception as exc:  # surface failures in the trace instead of hanging the stream
        run["error"] = str(exc)
        audit.append({"kind": "run_failed", "run_id": run_id, "error": str(exc)})
    finally:
        run["done"] = True


@app.post("/agent/run/{ticket_id}")
async def start_run(ticket_id: str, background: BackgroundTasks) -> dict:
    run_id = str(uuid.uuid4())
    runs[run_id] = {"run_id": run_id, "ticket_id": ticket_id, "events": [], "verdict": None, "evidence": [], "done": False}
    background.add_task(_execute, run_id, ticket_id)
    return {"run_id": run_id}


@app.get("/agent/runs/{run_id}")
def get_run(run_id: str) -> dict:
    if run_id not in runs:
        raise HTTPException(404, "unknown run")
    return runs[run_id]


@app.get("/agent/stream/{run_id}")
async def stream(run_id: str, request: Request) -> StreamingResponse:
    if run_id not in runs:
        raise HTTPException(404, "unknown run")

    async def gen():
        sent = 0
        while True:
            run = runs[run_id]
            while sent < len(run["events"]):
                yield f"data: {json.dumps(run['events'][sent])}\n\n"
                sent += 1
            if run["done"] and sent >= len(run["events"]):
                yield "event: end\ndata: {}\n\n"
                return
            if await request.is_disconnected():
                return
            yield ": ping\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------- evidence / citizen (stubs) ----------------
class PhotoRequest(BaseModel):
    ticket_id: str
    closure_photo_url: Optional[str] = None
    citizen_photo_url: Optional[str] = None


@app.post("/evidence/photo")
async def evidence_photo(req: PhotoRequest) -> dict:
    """STUB. AYUSH: imagehash + EXIF + CLIP."""
    score = await get_engine().get_score(req.ticket_id)
    return tools.stub_photo(req.ticket_id, score["p_false_closure"])


class CitizenSend(BaseModel):
    ticket_id: str
    channel: str = "telegram"


@app.post("/citizen/send")
def citizen_send(req: CitizenSend) -> dict:
    """STUB. AYUSH: Telegram first, then WhatsApp Cloud."""
    audit.append({"kind": "citizen_message_stub", "ticket_id": req.ticket_id, "channel": req.channel})
    return {"sent": False, "mode": "stub"}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict:
    await request.body()
    return {"ok": True, "mode": "stub"}


@app.get("/whatsapp/webhook")
def whatsapp_verify(request: Request) -> Any:
    """Meta verification handshake. AYUSH: compare hub.verify_token with your env value."""
    return int(request.query_params.get("hub.challenge", "0"))


# ---------------- approvals ----------------
class Decision(BaseModel):
    decision: str  # approve | reject
    note: Optional[str] = None


@app.get("/approvals")
def list_approvals(status: Optional[str] = None) -> list[dict]:
    return [a for a in approvals.values() if not status or a["status"] == status]


async def _outcome_check(approval_id: str, ticket_id: str) -> None:
    await asyncio.sleep(config.OUTCOME_DELAY_S)
    try:
        t = await get_engine().get_ticket(ticket_id)
        audit.append({"kind": "outcome_check", "approval_id": approval_id, "ticket_status": t["status"]})
    except Exception as exc:
        audit.append({"kind": "outcome_check_failed", "approval_id": approval_id, "error": str(exc)})


@app.post("/approvals/{approval_id}/decide")
async def decide(approval_id: str, body: Decision, background: BackgroundTasks) -> dict:
    a = approvals.get(approval_id)
    if a is None:
        raise HTTPException(404, "unknown approval")
    if a["status"] != "pending":
        raise HTTPException(409, f"already {a['status']}")
    if body.decision not in ("approve", "reject"):
        raise HTTPException(422, "decision must be approve or reject")
    a["note"] = body.note
    if body.decision == "reject":
        a["status"] = "rejected"
        audit.append({"kind": "approval_rejected", "approval_id": approval_id, "note": body.note})
        return a
    engine = get_engine()
    result = await (engine.reopen(a["ticket_id"]) if a["action"] == "reopen" else engine.escalate(a["ticket_id"]))
    a["status"] = "approved"
    a["municipal_result"] = result
    audit.append({"kind": "approval_approved", "approval_id": approval_id, "action": a["action"], "note": body.note})
    background.add_task(_outcome_check, approval_id, a["ticket_id"])
    return a


# ---------------- audit ----------------
@app.get("/audit")
def get_audit() -> list[dict]:
    return audit.rows


@app.get("/audit/verify")
def verify_audit() -> dict:
    return audit.verify()
