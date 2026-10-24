"""Module 3 (part): citizen channels (Telegram, shared with WhatsApp). Register a contact for a ticket, send the
"Was it fixed?" message with tap buttons, read the reply (button, number, free text, photo, voice note) into
Evidence, and answer the citizen like a normal bot: acknowledge, re-ask when unclear, handle /start, /help, STOP.

Demo contacts are our own registered chats; we never message real citizens. Only the hash of the chat id goes into
logs, the audit chain and any LLM prompt. Bot replies are best-effort: a failed acknowledgement never loses the
evidence.
"""
import hashlib
import logging
import threading
from typing import Callable

import httpx

from . import audit, citizen, config, events
from .db import get_conn, lock
from .models import Evidence, now_iso

log = logging.getLogger(__name__)

_client: httpx.Client | None = None
_client_lock = threading.Lock()


def _http() -> httpx.Client:
    """One kept-alive HTTPS connection to Telegram. A fresh connection per call cost 1.4 to 2.5 s each (TLS handshake)
    against 0.2 to 0.4 s on a reused one, which made every bot reply several seconds late."""
    global _client
    with _client_lock:
        if _client is None:
            _client = httpx.Client(timeout=httpx.Timeout(15.0, connect=8.0),
                                   limits=httpx.Limits(max_keepalive_connections=4, keepalive_expiry=120))
        return _client


def chat_hash(chat_id: str | int) -> str:
    return hashlib.sha1(str(chat_id).encode()).hexdigest()[:16]


# ---- Telegram API ----------------------------------------------------------------------------------------------
def _api(method: str, **payload) -> dict:
    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    r = _http().post(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}", json=payload)
    r.raise_for_status()
    return r.json()


def answer_buttons(ticket_id: str, lang: str) -> list[list[dict]]:
    yes, no, partly = citizen.button_labels(lang)
    return [[{"text": yes, "callback_data": f"ans:{ticket_id}:1"},
             {"text": no, "callback_data": f"ans:{ticket_id}:2"},
             {"text": partly, "callback_data": f"ans:{ticket_id}:3"}]]


def send_message(chat_id: str | int, text: str, buttons: list[list[dict]] | None = None) -> None:
    payload = {"chat_id": chat_id, "text": text}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    _api("sendMessage", **payload)


def deliver(channel: str, chat_id: str | int, text: str, buttons=None) -> bool:
    """Send one message or raise. Returns False when the channel is not configured (nothing to send with)."""
    if channel == "whatsapp":
        from . import whatsapp
        if not (config.WHATSAPP_TOKEN and config.WHATSAPP_PHONE_NUMBER_ID):
            return False
        whatsapp.send_text(str(chat_id), text)
        return True
    if not config.TELEGRAM_BOT_TOKEN:
        return False
    send_message(chat_id, text, buttons)
    return True


def _notify(channel: str, chat_id: str | int, text: str, buttons=None) -> None:
    """Best-effort bot reply to something the citizen just sent. Silent when the channel is not configured."""
    try:
        deliver(channel, chat_id, text, buttons)
    except Exception as exc:   # an undelivered acknowledgement must not break evidence handling
        log.warning("bot reply failed: %s", type(exc).__name__)


# ---- contacts and the first question ---------------------------------------------------------------------------
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
    """Send the question in the contact's language (with tap buttons on Telegram). False if no usable contact."""
    row = get_request(ticket_id)
    if row is None or row["status"] == "opted_out":
        return False
    text = citizen.build_prompt(row["lang"], category, area, date)
    if sender is not None:
        sender(row["chat_id"], text)
    elif row["channel"] == "whatsapp":
        from . import whatsapp
        whatsapp.send_text(row["chat_id"], text)
    else:
        send_message(row["chat_id"], text, answer_buttons(ticket_id, row["lang"]))
    with lock():
        # one open question per chat: a typed "2" must never be ambiguous. Older open questions are withdrawn, and
        # their buttons answer "no longer open" (see the stale-button path in handle_reply).
        superseded = get_conn().execute(
            "SELECT ticket_id FROM citizen_requests WHERE chat_id=? AND channel=? AND status='asked' AND ticket_id!=?",
            (row["chat_id"], row["channel"], ticket_id)).fetchall()
        get_conn().execute("UPDATE citizen_requests SET status='superseded' WHERE chat_id=? AND channel=? "
                           "AND status='asked' AND ticket_id!=?", (row["chat_id"], row["channel"], ticket_id))
        get_conn().execute("UPDATE citizen_requests SET status='asked', asked_at=? WHERE ticket_id=?",
                           (now_iso(), ticket_id))
        get_conn().commit()
    for old_row in superseded:
        audit.append("citizen_question_superseded", {"ticket_id": old_row["ticket_id"], "by": ticket_id,
                                                     "chat_hash": row["chat_hash"]})
    audit.append("citizen_message_sent", {"ticket_id": ticket_id, "chat_hash": row["chat_hash"]})
    return True


# ---- incoming messages -----------------------------------------------------------------------------------------
def handle_update(update: dict, fallback: Callable[[str], str | None] | None = None) -> Evidence | None:
    """Process one Telegram update (message or button tap). Returns Evidence when it answers an open question."""
    cq = update.get("callback_query")
    if cq:
        return _handle_button(cq, fallback)
    msg = update.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    if chat_id is None:
        return None
    text = (msg.get("text") or msg.get("caption") or "").strip()
    command = text.lower().split("@")[0]
    if command.startswith("/start ") and len(text.split()) == 2:   # deep link from the website: /start <one-time token>
        from . import cases
        if cases.claim_link(text.split()[1], chat_id) is None:
            _notify("telegram", chat_id, cases.BAD_LINK)
        return None
    if command in ("/start", "/help"):
        _notify("telegram", chat_id, citizen.ack_text(_lang_for(chat_id), "help" if command == "/help" else "idle"))
        return None
    if not text and msg.get("voice"):
        text = transcribe_voice(msg["voice"]["file_id"])
    from . import cases
    cases.follow_language(chat_id, text)
    image = _image_of(msg)
    if image:
        cases.receive_photo(chat_id, image)
        if not text:
            return None   # a bare photo is stored for a person to review; it never answers the question by itself
    return handle_reply("telegram", chat_id, text, bool(image), fallback)


def _image_of(msg: dict) -> dict | None:
    """The largest usable image in a message: a normal photo (Telegram strips its EXIF) or an image sent as a file."""
    if msg.get("photo"):
        sizes = [p for p in msg["photo"] if (p.get("file_size") or 0) <= config.MAX_PHOTO_BYTES] or msg["photo"][:1]
        return {"file_id": sizes[-1]["file_id"], "source": "photo", "size": sizes[-1].get("file_size") or 0}
    doc = msg.get("document") or {}
    if str(doc.get("mime_type", "")).startswith("image/"):
        return {"file_id": doc["file_id"], "source": "file", "size": doc.get("file_size") or 0}
    return None


def download_file(file_id: str) -> bytes:
    info = _http().get(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getFile", params={"file_id": file_id}).json()["result"]
    r = _http().get(f"https://api.telegram.org/file/bot{config.TELEGRAM_BOT_TOKEN}/{info['file_path']}", timeout=30)
    r.raise_for_status()
    return r.content


def _lang_for(chat_id: str | int, channel: str = "telegram") -> str:
    row = get_conn().execute("SELECT lang FROM citizen_requests WHERE chat_id=? AND channel=? "
                             "ORDER BY created_at DESC LIMIT 1", (str(chat_id), channel)).fetchone()
    return row["lang"] if row else "en"


def _handle_button(cq: dict, fallback) -> Evidence | None:
    chat_id = ((cq.get("message") or {}).get("chat") or {}).get("id")
    data = cq.get("data") or ""
    if config.TELEGRAM_BOT_TOKEN:
        try:   # stop the button's loading spinner immediately
            _api("answerCallbackQuery", callback_query_id=cq["id"])
        except Exception:
            pass
    if chat_id is None or not data.startswith("ans:"):
        return None
    ticket_id, _, n = data[len("ans:"):].rpartition(":")      # "ans:<ticket id>:<1|2|3>"
    ev = handle_reply("telegram", chat_id, n if n in ("1", "2", "3") else "", False, fallback, ticket_id=ticket_id)
    if config.TELEGRAM_BOT_TOKEN and cq.get("message"):   # remove the buttons so they cannot be tapped twice
        threading.Thread(target=_clear_buttons, args=(chat_id, cq["message"]["message_id"]), daemon=True).start()
    return ev


def _clear_buttons(chat_id, message_id) -> None:
    try:
        _api("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id, reply_markup={"inline_keyboard": []})
    except Exception:
        pass


def transcribe_voice(file_id: str, fetch=None, transcriber=None) -> str:
    """Download a Telegram voice note and transcribe it. Returns "" if anything fails (reply stays unparsed)."""
    from . import llm
    try:
        if fetch is None:
            info = httpx.get(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getFile",
                             params={"file_id": file_id}, timeout=10).json()["result"]
            fetch = lambda: httpx.get(f"https://api.telegram.org/file/bot{config.TELEGRAM_BOT_TOKEN}/"
                                      f"{info['file_path']}", timeout=20).content
        return (transcriber or llm.transcribe)(fetch())
    except Exception:
        return ""


def handle_reply(channel: str, chat_id: str | int, text: str, has_photo: bool = False,
                 fallback: Callable[[str], str | None] | None = None, ticket_id: str | None = None) -> Evidence | None:
    """Channel-independent: match a reply to the open question for this contact, record Evidence, answer the
    citizen. Unclear replies and photos keep the question open so the citizen can still answer it."""
    if ticket_id is not None:   # a button tap names its ticket
        row = get_conn().execute("SELECT * FROM citizen_requests WHERE ticket_id=? AND chat_id=? AND channel=? "
                                 "AND status='asked'", (ticket_id, str(chat_id), channel)).fetchone()
        if row is None:         # an old button on a question that is already answered or withdrawn
            _notify(channel, chat_id, citizen.ack_text(_lang_for(chat_id, channel), "stale"))
            return None
    else:
        row = get_conn().execute(
            "SELECT * FROM citizen_requests WHERE chat_id=? AND channel=? AND status='asked' "
            "ORDER BY asked_at DESC LIMIT 1", (str(chat_id), channel)).fetchone()
    if row is None:
        _notify(channel, chat_id, citizen.ack_text(_lang_for(chat_id, channel), "idle"))
        return None
    ticket_id, lang = row["ticket_id"], row["lang"]
    audit.append("citizen_reply_received", {"ticket_id": ticket_id, "chat_hash": row["chat_hash"],
                                            "has_photo": has_photo})
    if citizen.parse_intent(text) == "stop":
        with lock():
            get_conn().execute("UPDATE citizen_requests SET status='opted_out' WHERE ticket_id=?", (ticket_id,))
            get_conn().commit()
        _notify(channel, chat_id, citizen.ack_text(lang, "stop"))
        return None
    ev = citizen.reply_to_evidence(ticket_id, text, fallback, has_photo)
    again = answer_buttons(ticket_id, lang) if channel == "telegram" else None
    if ev.verdict == "inconclusive":   # not a yes/no/partly: keep the question open and help them answer
        _notify(channel, chat_id, citizen.ack_text(lang, "photo" if has_photo and not text else "unclear"), again)
        return None
    with lock():
        get_conn().execute("UPDATE citizen_requests SET status='answered', answered_at=? WHERE ticket_id=?",
                           (now_iso(), ticket_id))
        get_conn().execute("INSERT INTO evidence VALUES (?,?,?,?,?)",
                           (ev.evidence_id, ticket_id, None, ev.model_dump_json(), ev.created_at))
        get_conn().commit()
    audit.append("tool_result", {"ticket_id": ticket_id, "tool": "ask_citizen", "evidence_id": ev.evidence_id,
                                 "check": ev.check, "verdict": ev.verdict, "lr": ev.likelihood_ratio})
    events.record(ticket_id, "citizen_reply", f"The citizen answered: {ev.details['intent'].replace('_', ' ')}.")
    _notify(channel, chat_id, citizen.ack_text(lang, ev.details["intent"]))
    return ev


def poll_once(offset: int | None = None, timeout: int = 20) -> tuple[list[dict], int | None]:
    """Long-poll getUpdates (no public URL needed). Returns (updates, next_offset)."""
    payload = {"timeout": timeout, "allowed_updates": ["message", "callback_query"],
               **({"offset": offset} if offset else {})}
    r = _http().post(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates", json=payload,
                     timeout=timeout + 10)
    r.raise_for_status()
    updates = r.json()["result"]
    return updates, (updates[-1]["update_id"] + 1 if updates else offset)
