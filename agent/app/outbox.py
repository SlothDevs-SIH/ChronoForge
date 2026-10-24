"""Reliable citizen messages. A message is sent at once; if the channel fails it is queued and retried with backoff
instead of being dropped. A permanent refusal (the citizen blocked the bot) is not retried."""
import json
import logging
import time

import httpx

from . import config, events, telegram
from .db import get_conn, lock
from .models import now_iso

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 5
BACKOFF_SECONDS = (10, 30, 120, 600)   # wait before attempt 2, 3, 4, 5


def _permanent(exc: Exception) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (400, 401, 403, 404)


def send(ticket_id: str | None, channel: str, chat_id, text: str, buttons=None) -> bool:
    """True if delivered now or queued for retry; False if the channel is not configured or the citizen blocked us."""
    try:
        return telegram.deliver(channel, chat_id, text, buttons) is not False
    except Exception as exc:
        if _permanent(exc):
            log.warning("message refused for good: %s", type(exc).__name__)
            return False
        with lock():
            get_conn().execute(
                "INSERT INTO outbox (ticket_id, channel, chat_id, text, buttons, attempts, next_try, status, last_error, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ticket_id, channel, str(chat_id), text, json.dumps(buttons) if buttons else None, 1,
                 time.time() + BACKOFF_SECONDS[0], "pending", type(exc).__name__, now_iso()))
            get_conn().commit()
        return True


def process_due(now: float | None = None) -> int:
    """Retry every queued message that is due. Returns how many were delivered."""
    now = time.time() if now is None else now
    delivered = 0
    rows = get_conn().execute("SELECT * FROM outbox WHERE status='pending' AND next_try<=? ORDER BY id LIMIT 50", (now,)).fetchall()
    for r in rows:
        status, err, attempts, next_try = "sent", None, r["attempts"] + 1, r["next_try"]
        try:
            telegram.deliver(r["channel"], r["chat_id"], r["text"], json.loads(r["buttons"]) if r["buttons"] else None)
            delivered += 1
        except Exception as exc:
            err = type(exc).__name__
            if _permanent(exc) or attempts >= MAX_ATTEMPTS:
                status = "failed"
            else:
                status, next_try = "pending", now + BACKOFF_SECONDS[min(attempts - 1, len(BACKOFF_SECONDS) - 1)]
        with lock():
            get_conn().execute("UPDATE outbox SET status=?, attempts=?, next_try=?, last_error=? WHERE id=?",
                               (status, attempts, next_try, err, r["id"]))
            get_conn().commit()
        if status == "failed" and r["ticket_id"]:
            events.record(r["ticket_id"], "message_failed", "A message to the citizen could not be delivered.", "staff")
    return delivered


def stats() -> dict:
    rows = get_conn().execute("SELECT status, COUNT(*) AS n FROM outbox GROUP BY status").fetchall()
    out = {"pending": 0, "sent": 0, "failed": 0}
    out.update({r["status"]: r["n"] for r in rows})
    return out
