"""Per-case timeline: every notable thing that happened to a ticket, in order. Citizen-visible entries are what the
citizen sees on their page; staff-only entries (internal decisions) are for officers and admins."""
from . import config
from .db import get_conn, lock
from .models import now_iso


def record(ticket_id: str, kind: str, text: str, audience: str = "citizen") -> None:
    with lock():
        get_conn().execute("INSERT INTO case_events (ticket_id, ts, kind, text, audience) VALUES (?,?,?,?,?)",
                           (ticket_id, now_iso(), kind, text, audience))
        get_conn().commit()


def timeline(ticket_id: str, staff: bool) -> list[dict]:
    q = "SELECT ts, kind, text, audience FROM case_events WHERE ticket_id=?"
    if not staff:
        q += " AND audience='citizen'"
    return [dict(r) for r in get_conn().execute(q + " ORDER BY id", (ticket_id,)).fetchall()]
