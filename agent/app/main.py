"""Agent service (port 8002). Run: uvicorn app.main:app --port 8002"""
import asyncio
import json
import threading
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from pydantic import BaseModel

from . import agent, approvals, audit, config, llm, llm_planner, telegram, tools, whatsapp
from .db import get_conn, lock
from .models import DecideRequest, PhotoRequest
from .photo import PhotoIndex, check_ref_allowed, verify_photo

def require_admin(x_admin_token: str | None = Header(default=None)):
    """Optional shared secret (AGENT_ADMIN_TOKEN). Unset = open, which is only acceptable on a laptop demo."""
    if config.ADMIN_TOKEN and x_admin_token != config.ADMIN_TOKEN:
        raise HTTPException(403, "admin token required")


app = FastAPI(title="TrueClose Agent service")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"ok": True, "service": "agent", "stubs": config.USE_STUBS}


@app.post("/evidence/photo", dependencies=[Depends(require_admin)])
def evidence_photo(req: PhotoRequest):
    ticket = tools._get_ticket(req.ticket_id)
    try:
        check_ref_allowed(req.closure_photo_url)
    except ValueError as exc:
        raise HTTPException(403, str(exc))
    try:
        return verify_photo(req.ticket_id, req.closure_photo_url, ticket, PhotoIndex())
    except Exception as exc:
        raise HTTPException(422, f"could not read photo: {exc}")


class ContactRequest(BaseModel):
    chat_id: str
    lang: str = "en"
    channel: str = "telegram"


@app.post("/citizen/{ticket_id}/contact", dependencies=[Depends(require_admin)])
def register_contact(ticket_id: str, req: ContactRequest):
    """Demo only: link a ticket to one of our own registered Telegram chats."""
    telegram.register_contact(ticket_id, req.chat_id, req.lang, req.channel)
    return {"ticket_id": ticket_id, "chat_hash": telegram.chat_hash(req.chat_id)}


class SendRequest(BaseModel):
    ticket_id: str
    category: str = "issue"
    area: str = "your area"
    date: str = "recently"


@app.post("/citizen/send", dependencies=[Depends(require_admin)])
def citizen_send(req: SendRequest):
    """Contract endpoint: send the "Was it fixed?" message for a ticket (contact must be registered)."""
    return ask_now(req.ticket_id, AskRequest(category=req.category, area=req.area, date=req.date))


class AskRequest(BaseModel):
    category: str = "pothole"
    area: str = "your area"
    date: str = "recently"


@app.post("/citizen/{ticket_id}/ask", dependencies=[Depends(require_admin)])
def ask_now(ticket_id: str, req: AskRequest):
    """Demo trigger: send the "Was it fixed?" message to the registered contact."""
    if not telegram.send_request(ticket_id, req.category, req.area, req.date):
        raise HTTPException(409, "no usable contact for this ticket")
    return {"sent": True}


@app.post("/telegram/webhook")
@app.post("/channels/telegram/webhook")
def telegram_webhook(update: dict, x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    if config.TELEGRAM_WEBHOOK_SECRET and x_telegram_bot_api_secret_token != config.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(403, "bad secret")
    ev, run_id = process_telegram_update(update)
    if ev is None:
        return {"ok": True, "evidence": None}
    return {"ok": True, "evidence_id": ev.evidence_id, "run_id": run_id}


def process_telegram_update(update: dict):
    fallback = llm_planner.classify_reply if llm.available_providers() else None
    ev = telegram.handle_update(update, fallback)
    if ev is None:
        return None, None
    run_id = agent.start_run(ev.ticket_id)   # re-run so the new evidence is fused into a fresh verdict
    agent.run_in_background(run_id)
    return ev, run_id


def _load_offset() -> int | None:
    row = get_conn().execute("SELECT v FROM kv WHERE k='telegram_offset'").fetchone()
    return int(row["v"]) if row else None


def _save_offset(offset: int) -> None:
    with lock():
        get_conn().execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('telegram_offset', ?)", (str(offset),))
        get_conn().commit()


def _poll_loop():
    """Long-poll Telegram. The offset is saved BEFORE an update is processed, so a restart never replays an old
    button tap or reply onto a newer question; updates run on a small pool so a slow one (an LLM call) cannot
    delay the bot's reply to the next person."""
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tg-update")
    offset = _load_offset()
    while True:
        try:
            updates, offset = telegram.poll_once(offset)
            if updates and offset:
                _save_offset(offset)
            for u in updates:
                pool.submit(_safe_process, u)
        except Exception:
            time.sleep(3)


def _safe_process(update: dict) -> None:
    try:
        process_telegram_update(update)
    except Exception:
        pass


@app.on_event("startup")
def start_polling():
    if config.TELEGRAM_POLLING and config.TELEGRAM_BOT_TOKEN:
        threading.Thread(target=_poll_loop, daemon=True).start()


@app.get("/whatsapp/webhook")
@app.get("/channels/whatsapp/webhook")
def whatsapp_verify(hub_mode: str | None = Query(default=None, alias="hub.mode"),
                    hub_token: str | None = Query(default=None, alias="hub.verify_token"),
                    hub_challenge: str | None = Query(default=None, alias="hub.challenge")):
    if hub_mode == "subscribe" and config.WHATSAPP_VERIFY_TOKEN and hub_token == config.WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge or "")
    raise HTTPException(403, "verification failed")


@app.post("/whatsapp/webhook")
@app.post("/channels/whatsapp/webhook")
def whatsapp_webhook(payload: dict):
    fallback = llm_planner.classify_reply if llm.available_providers() else None
    run_ids = []
    for m in whatsapp.parse_payload(payload):
        ev = telegram.handle_reply("whatsapp", m["wa_id"], m["text"], m["has_photo"], fallback)
        if ev is not None:
            run_id = agent.start_run(ev.ticket_id)
            agent.run_in_background(run_id)
            run_ids.append(run_id)
    return {"ok": True, "run_ids": run_ids}


@app.post("/agent/run/{ticket_id}")
def run_ticket(ticket_id: str):
    run_id = agent.start_run(ticket_id)
    agent.run_in_background(run_id)
    return {"run_id": run_id}


@app.get("/agent/stream/{run_id}")
async def stream(run_id: str):
    run = agent.RUNS.get(run_id)
    if run is None:
        row = get_conn().execute("SELECT status, trace FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "unknown run")

        async def replay():
            for ev in json.loads(row["trace"]):
                yield {"event": "trace", "data": json.dumps(ev)}
            yield {"event": "end", "data": json.dumps({"status": row["status"]})}
        return EventSourceResponse(replay())

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


@app.post("/approvals/{approval_id}/decide", dependencies=[Depends(require_admin)])
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
