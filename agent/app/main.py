"""Agent service (port 8002). Run: uvicorn app.main:app --port 8002"""
import asyncio
import json
import threading

import httpx
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from pydantic import BaseModel

from . import agent, approvals, audit, auth, cases, config, events, explain, outbox, ratelimit, summary, llm, llm_planner, telegram, tools, whatsapp
from .db import get_conn, lock
from .models import DecideRequest, PhotoRequest
from .photo import PhotoIndex, check_ref_allowed, verify_photo

def require_admin(x_admin_token: str | None = Header(default=None)):
    """Optional shared secret (AGENT_ADMIN_TOKEN). Unset = open, which is only acceptable on a laptop demo."""
    if config.ADMIN_TOKEN and x_admin_token != config.ADMIN_TOKEN:
        raise HTTPException(403, "admin token required")


app = FastAPI(title="TrueClose Agent service")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


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


@app.post("/agent/run/{ticket_id}", dependencies=[Depends(auth.require_role("officer", "admin"))])
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


@app.get("/approvals", dependencies=[Depends(auth.require_role("officer", "admin"))])
def list_approvals(status: str | None = "pending"):
    out = approvals.list_approvals(status)
    for a in out:   # plain-language reasons, built only from the recorded evidence
        a["explain"] = explain.for_verdict(a["verdict_snapshot"])
    return out


@app.post("/approvals/{approval_id}/decide", dependencies=[Depends(require_admin), Depends(auth.require_role("officer", "admin"))])
def decide(approval_id: str, req: DecideRequest):
    try:
        return approvals.decide(approval_id, req.decision, req.note)
    except KeyError:
        raise HTTPException(404, "unknown approval")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/outcomes", dependencies=[Depends(auth.require_role("officer", "admin"))])
def outcomes():
    return approvals.outcomes()


@app.get("/audit", dependencies=[Depends(auth.require_role("officer", "admin"))])
def get_audit(limit: int = 500):
    return audit.entries(limit)


@app.get("/audit/verify")
def verify_audit():
    return audit.verify()


class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str
    role: str = "citizen"


class LoginRequest(BaseModel):
    email: str
    password: str


class StatusRequest(BaseModel):
    status: str


class TicketRef(BaseModel):
    ticket_id: str


@app.on_event("startup")
def seed_first_admin():
    auth.seed_admin()


@app.post("/auth/register", dependencies=[Depends(ratelimit.limit("register", 8, 60))])
def register(req: RegisterRequest):
    try:
        return auth.register(req.email, req.name, req.password, req.role)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/auth/login", dependencies=[Depends(ratelimit.limit("login", 10, 60))])
def login(req: LoginRequest):
    try:
        return auth.login(req.email, req.password)
    except PermissionError as exc:
        raise HTTPException(401, str(exc))


@app.get("/auth/me")
def me(user=Depends(auth.current_user)):
    if user is None:
        raise HTTPException(401, "sign in required")
    return user


@app.get("/admin/users")
def admin_users(_=Depends(auth.require_role("admin"))):
    return auth.list_users()


@app.post("/admin/users/{user_id}/status")
def admin_set_status(user_id: str, req: StatusRequest, _=Depends(auth.require_role("admin"))):
    if req.status not in ("active", "disabled"):
        raise HTTPException(400, "status must be active or disabled")
    try:
        return auth.set_status(user_id, req.status)
    except KeyError:
        raise HTTPException(404, "unknown user")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/me/tickets")
def my_tickets(user=Depends(auth.require_role("citizen"))):
    return auth.my_tickets(user["user_id"])


@app.post("/me/tickets")
def add_my_ticket(req: TicketRef, user=Depends(auth.require_role("citizen"))):
    try:
        auth.add_ticket(user["user_id"], req.ticket_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return auth.my_tickets(user["user_id"])


class NewCase(BaseModel):
    category: str
    text: str
    ward: str = "unspecified"
    lat: float | None = None
    lng: float | None = None


@app.on_event("startup")
def start_case_watcher():
    cases.start_watcher()


@app.post("/me/requests")
def submit_request(req: NewCase, user=Depends(auth.require_role("citizen"))):
    """A citizen files a request on the website. Returns the ticket and a one-time link that connects Telegram."""
    ratelimit.check_user("request", user["user_id"], config.REQUESTS_PER_HOUR, 3600)
    try:
        return cases.submit(user["user_id"], req.category, req.text, req.ward, req.lat, req.lng)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except ConnectionError as exc:
        raise HTTPException(503, str(exc))


@app.post("/me/requests/{ticket_id}/telegram-link")
def telegram_link(ticket_id: str, user=Depends(auth.require_role("citizen"))):
    if ticket_id not in auth.my_tickets(user["user_id"]):
        raise HTTPException(404, "unknown request")
    return cases.new_link(ticket_id)


@app.post("/admin/requests/{ticket_id}/close")
def admin_close_request(ticket_id: str, _=Depends(auth.require_role("admin"))):
    """Demo: stand in for the city closing a website request, which the watcher then picks up."""
    try:
        return cases.close_for_demo(ticket_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except Exception:
        raise HTTPException(503, "the Engine is not reachable")


@app.get("/ready")
def ready():
    """Readiness for a host's health check: the database answers and the Engine is reachable (if real services are on)."""
    problems = []
    try:
        get_conn().execute("SELECT 1").fetchone()
    except Exception:
        problems.append("database")
    if not config.USE_STUBS:
        try:
            httpx.get(f"{config.ENGINE_URL}/health", timeout=3).raise_for_status()
        except Exception:
            problems.append("engine")
    if problems:
        raise HTTPException(503, "not ready: " + ", ".join(problems))
    return {"ok": True, "auth_secret_set": bool(config.AUTH_SECRET), "telegram": bool(config.TELEGRAM_BOT_TOKEN)}


@app.post("/approvals/{approval_id}/retry", dependencies=[Depends(auth.require_role("officer", "admin"))])
def retry_approval(approval_id: str):
    try:
        return approvals.retry(approval_id)
    except KeyError:
        raise HTTPException(404, "unknown approval")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/cases/{ticket_id}/timeline")
def case_timeline_staff(ticket_id: str, _=Depends(auth.require_role("officer", "admin"))):
    return events.timeline(ticket_id, staff=True)


@app.get("/me/requests/{ticket_id}/timeline")
def case_timeline_citizen(ticket_id: str, user=Depends(auth.require_role("citizen"))):
    if ticket_id not in auth.my_tickets(user["user_id"]):
        raise HTTPException(404, "unknown request")
    return events.timeline(ticket_id, staff=False)


@app.get("/cases/{ticket_id}/photos")
def case_photos(ticket_id: str, _=Depends(auth.require_role("officer", "admin"))):
    return cases.photos_for(ticket_id)


@app.get("/me/requests/similar")
def similar_requests(category: str, text: str, ward: str = "", user=Depends(auth.require_role("citizen"))):
    """Before filing: open website requests that look like the same problem, so the citizen can follow one instead."""
    try:
        r = httpx.get(f"{config.ENGINE_URL}/requests/similar", params={"category": category, "text": text, "ward": ward}, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []   # the check is a convenience: if it cannot run, filing must still work


@app.get("/admin/summary")
def admin_summary(days: int = 7, _=Depends(auth.require_role("admin"))):
    return summary.build(max(1, min(days, 365)))
