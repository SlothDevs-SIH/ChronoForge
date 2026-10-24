"""Digest for administrators: what happened over the last N days, counted from the case timeline."""
from datetime import datetime, timedelta, timezone

from . import outbox
from .db import get_conn

KINDS = {
    "submitted": "requests filed",
    "telegram_linked": "Telegram connections",
    "closed": "closures detected",
    "verdict_verified_fixed": "confirmed really fixed",
    "verdict_likely_not_fixed": "found probably not fixed",
    "verdict_cannot_tell": "inconclusive",
    "reopened": "reopened by an administrator",
    "reopen_rejected": "reopen rejected",
    "photo_received": "citizen photos",
    "reminder_sent": "reminders sent",
    "silence_escalated": "escalated after silence",
}


def build(days: int = 7) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = get_conn().execute("SELECT kind, COUNT(*) AS n FROM case_events WHERE ts>=? GROUP BY kind", (since,)).fetchall()
    counts = {k: 0 for k in KINDS}
    counts.update({r["kind"]: r["n"] for r in rows if r["kind"] in KINDS})
    checked = counts["verdict_verified_fixed"] + counts["verdict_likely_not_fixed"]
    rate = round(counts["verdict_likely_not_fixed"] / checked, 3) if checked else None
    pending = get_conn().execute("SELECT COUNT(*) AS n FROM approvals WHERE status='pending'").fetchone()["n"]
    delivery = outbox.stats()
    text = (f"Last {days} days: {counts['submitted']} requests filed, {counts['closed']} closures detected. "
            f"Of {checked} closures with a conclusive check, {counts['verdict_likely_not_fixed']} looked probably not fixed"
            + (f" ({rate:.0%})" if rate is not None else "") + f" and {counts['verdict_verified_fixed']} were confirmed. "
            f"{counts['reopened']} reopened. {pending} approvals are waiting."
            + (f" {delivery['failed']} citizen messages could not be delivered." if delivery["failed"] else ""))
    return {"days": days, "counts": counts, "labels": KINDS, "not_fixed_rate": rate, "pending_approvals": pending,
            "messages": delivery, "text": text}
