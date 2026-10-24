"""Citizen reply links: a signed, expiring, single-use link that lets someone answer "Was it fixed?" without an account.

The link only proves "an officer sent this person this question about this ticket". The answer goes through the same
path as a Telegram reply (citizen.reply_to_evidence -> evidence row -> audit -> a fresh agent run), so the likelihood
ratios are the existing ones and nothing else about verification changes.
"""
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import audit, citizen, config
from .auth import Principal, require_staff, valid_ticket_id
from .db import get_conn, lock
from .http_utils import api_error, rate_limit
from .models import now_iso

router = APIRouter()


def _secret() -> bytes:
    if config.REPLY_LINK_SECRET:
        return config.REPLY_LINK_SECRET.encode()
    if config.AUTH_REQUIRED:
        raise api_error(503, "reply_links_not_configured", "REPLY_LINK_SECRET is not set on the server.")
    return b"local-development-reply-secret"   # only when auth is off (a laptop demo)


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(token_id: str, ticket_id: str, lang: str, exp: int) -> str:
    body = _b64(json.dumps({"j": token_id, "t": ticket_id, "e": exp, "l": lang}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def parse_token(token: str) -> dict:
    """Signature first (constant time), then the payload. Any tampering is the same plain 404."""
    bad = api_error(404, "invalid_link", "This link is not valid.")
    try:
        body, sig = token.split(".", 1)
        good = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            raise bad
        data = json.loads(_unb64(body))
        return {"token_id": str(data["j"]), "ticket_id": str(data["t"]), "exp": int(data["e"]), "lang": str(data["l"])}
    except (ValueError, KeyError, TypeError):
        raise bad


def _link_row(token_id: str):
    return get_conn().execute("SELECT * FROM reply_links WHERE token_id=?", (token_id,)).fetchone()


def _status(data: dict, row) -> str:
    if row is None:
        raise api_error(404, "invalid_link", "This link is not valid.")
    if row["used_at"]:
        return "answered"
    return "expired" if data["exp"] < time.time() else "open"


class LinkRequest(BaseModel):
    ticket_id: str
    lang: Literal["en", "hi", "mr", "kn"] = "en"
    ttl_hours: int = Field(default=336, ge=1, le=24 * 60)


@router.post("/citizen/reply-links", tags=["citizen"])
def create_link(req: LinkRequest, p: Principal = Depends(require_staff)):
    """An officer makes a reply link for one ticket (send it to the citizen by any channel)."""
    valid_ticket_id(req.ticket_id)
    token_id = uuid4().hex
    exp = int(time.time()) + req.ttl_hours * 3600
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=req.ttl_hours)).isoformat().replace("+00:00", "Z")
    token = make_token(token_id, req.ticket_id, req.lang, exp)
    with lock():
        get_conn().execute("INSERT INTO reply_links (token_id, ticket_id, lang, expires_at, created_by, created_at) "
                           "VALUES (?,?,?,?,?,?)", (token_id, req.ticket_id, req.lang, expires_at, p.user_id, now_iso()))
        get_conn().commit()
    audit.append("reply_link_created", {"ticket_id": req.ticket_id, "token_id": token_id, "by": p.user_id})
    return {"token": token, "expires_at": expires_at}


@router.get("/reply/{token}", tags=["citizen"], dependencies=[Depends(rate_limit("reply", 30, 60))])
def reply_info(token: str):
    data = parse_token(token)
    status = _status(data, _link_row(data["token_id"]))
    from .verification import _ticket_info   # the city's record, or None when it cannot be read
    t = _ticket_info(data["ticket_id"]) or {}
    return {"ticket_id": data["ticket_id"], "category": t.get("category"), "ward": t.get("ward"),
            "lang": data["lang"], "status": status}


class ReplyRequest(BaseModel):
    answer: Literal["yes", "partly", "no"]
    lang: Literal["en", "hi", "mr", "kn"] | None = None


@router.post("/reply/{token}", tags=["citizen"], dependencies=[Depends(rate_limit("reply", 30, 60))])
def reply_submit(token: str, req: ReplyRequest):
    from . import agent
    data = parse_token(token)
    with lock():   # check-and-mark under one lock so a double tap cannot record two answers
        row = _link_row(data["token_id"])
        status = _status(data, row)
        if status == "answered":
            raise api_error(410, "link_used", "This question has already been answered.")
        if status == "expired":
            raise api_error(410, "link_expired", "This link has expired.")
        ev = citizen.reply_to_evidence(data["ticket_id"], req.answer)   # same keyword map and likelihood ratios as Telegram
        get_conn().execute("UPDATE reply_links SET used_at=? WHERE token_id=?", (now_iso(), data["token_id"]))
        get_conn().execute("INSERT INTO evidence VALUES (?,?,?,?,?)",
                           (ev.evidence_id, data["ticket_id"], None, ev.model_dump_json(), ev.created_at))
        get_conn().execute("UPDATE citizen_requests SET status='answered', answered_at=? WHERE ticket_id=? AND status='asked'",
                           (now_iso(), data["ticket_id"]))
        get_conn().commit()
    audit.append("citizen_reply_received", {"ticket_id": data["ticket_id"], "channel": "reply_link",
                                            "token_id": data["token_id"], "has_photo": False})
    audit.append("tool_result", {"ticket_id": data["ticket_id"], "tool": "ask_citizen", "evidence_id": ev.evidence_id,
                                 "check": ev.check, "verdict": ev.verdict, "lr": ev.likelihood_ratio})
    run_id = agent.start_run(data["ticket_id"])   # re-run so the new evidence is fused into a fresh verdict
    agent.run_in_background(run_id)
    return {"ok": True, "evidence_id": ev.evidence_id}   # no run id: that is for staff only
