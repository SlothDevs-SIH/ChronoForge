"""Module 3 (part): Telegram channel. Register a contact for a ticket, send the "Was it fixed?" message,
parse the webhook reply into Evidence. Demo contacts are our own registered chats; we never message real
citizens. Only the hash of the chat id goes into logs, the audit chain and any LLM prompt.
"""
import hashlib
from typing import Callable

import httpx

from . import audit, citizen, config
from .db import get_conn, lock
from .models import Evidence, now_iso


def chat_hash(chat_id: str | int) -> str:
    return hashlib.sha1(str(chat_id).encode()).hexdigest()[:16]


def send_message(chat_id: str | int, text: str) -> None:
    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    r = httpx.post(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
                   json={"chat_id": chat_id, "text": text}, timeout=10)
    r.raise_for_status()


def register_contact(ticket_id: str, chat_id: str | int, lang: str = "en", channel: str = "telegram") -> None:
    with lock():
        get_conn().execute(
            "INSERT OR REPLACE INTO citizen_requests (ticket_id, chat_id, chat_hash, lang, channel, status, created_at) "
            "VALUES (?,?,?,?,?, 'registered', ?)",
            (ticket_id, str(chat_id), chat_hash(chat_id), lang, channel, now_iso()))
        get_conn().commit()


def get_request(ticket_id: str):
    return get_conn().execute("SELECT * FROM citizen_requests WHERE ticket_id=?", (ticket_id,)).fetchone()


def has_contact(ticket_id: str) -> bool:
    row = get_request(ticket_id)
    return row is not None and row["status"] != "opted_out"


def send_request(ticket_id: str, category: str, area: str, date: str,
                 sender: Callable[[str | int, str], None] | None = None) -> bool:
    """Send the prompt in the contact's language. Returns False if there is no usable contact."""
    row = get_request(ticket_id)
    if row is None or row["status"] == "opted_out":
        return False
    if sender is None:
        from . import whatsapp
        sender = whatsapp.send_text if row["channel"] == "whatsapp" else send_message
    sender(row["chat_id"], citizen.build_prompt(row["lang"], category, area, date))
    with lock():
        get_conn().execute("UPDATE citizen_requests SET status='asked', asked_at=? WHERE ticket_id=?",
                           (now_iso(), ticket_id))
        get_conn().commit()
    audit.append("citizen_message_sent", {"ticket_id": ticket_id, "chat_hash": row["chat_hash"]})
    return True


def handle_update(update: dict, fallback: Callable[[str], str | None] | None = None) -> Evidence | None:
    """Process one Telegram webhook update. Returns Evidence when the reply answers an open request."""
    msg = update.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    if chat_id is None:
        return None
    return handle_reply("telegram", chat_id, msg.get("text") or msg.get("caption") or "",
                        bool(msg.get("photo")), fallback)


def handle_reply(channel: str, chat_id: str | int, text: str, has_photo: bool = False,
                 fallback: Callable[[str], str | None] | None = None) -> Evidence | None:
    """Channel-independent: match a reply to the open request for this contact and turn it into Evidence."""
    row = get_conn().execute(
        "SELECT * FROM citizen_requests WHERE chat_id=? AND channel=? AND status='asked' "
        "ORDER BY asked_at DESC LIMIT 1", (str(chat_id), channel)).fetchone()
    if row is None:
        return None
    ticket_id = row["ticket_id"]
    audit.append("citizen_reply_received", {"ticket_id": ticket_id, "chat_hash": row["chat_hash"],
                                            "has_photo": has_photo})
    if citizen.parse_intent(text) == "stop":
        with lock():
            get_conn().execute("UPDATE citizen_requests SET status='opted_out' WHERE ticket_id=?", (ticket_id,))
            get_conn().commit()
        return None
    ev = citizen.reply_to_evidence(ticket_id, text, fallback, has_photo)
    with lock():
        get_conn().execute("UPDATE citizen_requests SET status='answered', answered_at=? WHERE ticket_id=?",
                           (now_iso(), ticket_id))
        get_conn().execute("INSERT INTO evidence VALUES (?,?,?,?,?)",
                           (ev.evidence_id, ticket_id, None, ev.model_dump_json(), ev.created_at))
        get_conn().commit()
    audit.append("tool_result", {"ticket_id": ticket_id, "tool": "ask_citizen", "evidence_id": ev.evidence_id,
                                 "check": ev.check, "verdict": ev.verdict, "lr": ev.likelihood_ratio})
    return ev
