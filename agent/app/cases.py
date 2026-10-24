"""Website requests and case tracking.

  submit        a signed-in citizen files a request -> a ticket in the Engine ("web" city) -> a one-time Telegram link
  link          the citizen taps the link, the bot links their chat to the ticket and confirms the submission
  watch         a background loop notices when the city closes a tracked ticket and starts a verification run
  reopen        the run only ever PROPOSES a reopen; an admin approves it on the Approvals page, then the citizen is told

Nothing here reopens a ticket by itself. The verdict thresholds and likelihood ratios are the Agent's existing ones.
"""
import logging
import secrets
import threading
import time

import httpx

from . import agent, approvals, auth, config, telegram
from .db import get_conn, lock

log = logging.getLogger(__name__)

SUBMITTED = ("✅ Your request {ticket_id} has been submitted successfully.\n\n"
             "When the city marks it as fixed, TrueClose will check that it was really fixed and message you here. "
             "If it was not, an administrator can have it reopened.")
CLOSED_NOTICE = ("🔔 The city marked your request {ticket_id} as closed. TrueClose will now check that the work was "
                 "really done, and may ask you a question here.")
REOPENED = ("🔁 Your request {ticket_id} has been reopened. An administrator reviewed the evidence and agreed it was "
            "not properly fixed.")
BAD_LINK = "This link has expired or was already used. Open your request on the TrueClose website to get a new one."

_bot_username: str | None = None


def _engine_headers() -> dict:
    return {"X-Admin-Token": config.ENGINE_ADMIN_TOKEN} if config.ENGINE_ADMIN_TOKEN else {}


def bot_username() -> str | None:
    global _bot_username
    if _bot_username is None and config.TELEGRAM_BOT_TOKEN:
        try:
            _bot_username = telegram._api("getMe")["result"]["username"]
        except Exception:
            return None
    return _bot_username


def submit(user_id: str, category: str, text: str, ward: str, lat: float | None, lng: float | None) -> dict:
    """Create the ticket in the Engine and attach it to the citizen. Raises ValueError with a message for the user."""
    try:
        r = httpx.post(f"{config.ENGINE_URL}/requests", headers=_engine_headers(), timeout=10,
                       json={"category": category, "text": text, "ward": ward, "lat": lat, "lng": lng})
    except httpx.HTTPError:
        raise ConnectionError("the request service is not reachable right now, try again in a moment")
    if r.status_code in (422, 400):
        raise ValueError("describe the problem in a few words and pick a category")
    r.raise_for_status()
    ticket = r.json()
    auth.add_ticket(user_id, ticket["ticket_id"])
    return {"ticket": ticket, **new_link(ticket["ticket_id"])}


def new_link(ticket_id: str) -> dict:
    """A single-use token that lets one Telegram chat claim this ticket."""
    token = secrets.token_urlsafe(12)
    with lock():
        get_conn().execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (f"link:{token}", ticket_id))
        get_conn().commit()
    name = bot_username()
    return {"link_token": token, "telegram_link": f"https://t.me/{name}?start={token}" if name else None,
            "linked": telegram.has_contact(ticket_id)}


def claim_link(token: str, chat_id) -> str | None:
    """Called when someone opens the bot with ?start=<token>. Returns the ticket id, or None for a bad token."""
    with lock():
        row = get_conn().execute("SELECT v FROM kv WHERE k=?", (f"link:{token}",)).fetchone()
        if row is None:
            return None
        get_conn().execute("DELETE FROM kv WHERE k=?", (f"link:{token}",))
        get_conn().commit()
    ticket_id = row["v"]
    telegram.register_contact(ticket_id, chat_id)
    telegram._notify("telegram", chat_id, SUBMITTED.format(ticket_id=ticket_id))
    return ticket_id


def notify(ticket_id: str, template: str) -> bool:
    row = telegram.get_request(ticket_id)
    if row is None or row["status"] == "opted_out":
        return False
    telegram._notify(row["channel"], row["chat_id"], template.format(ticket_id=ticket_id))
    return True


# ---- watcher ---------------------------------------------------------------------------------------------------
def tracked_tickets() -> list[str]:
    conn = get_conn()
    ids = {r["ticket_id"] for r in conn.execute("SELECT ticket_id FROM user_tickets")}
    ids |= {r["ticket_id"] for r in conn.execute("SELECT ticket_id FROM citizen_requests WHERE status!='opted_out'")}
    return sorted(ids)


def _seen(ticket_id: str) -> str | None:
    row = get_conn().execute("SELECT v FROM kv WHERE k=?", (f"watch:{ticket_id}",)).fetchone()
    return row["v"] if row else None


def _mark(ticket_id: str, closed_at: str) -> None:
    with lock():
        get_conn().execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (f"watch:{ticket_id}", closed_at))
        get_conn().commit()


def tick(fetch_ticket=None) -> list[str]:
    """One pass: for every tracked ticket the city has newly closed, tell the citizen and start ONE verification run.
    A closure is handled once (keyed on its closed_at), and never while an approval for the ticket is already open.
    Returns the ticket ids a run was started for."""
    from . import tools
    fetch = fetch_ticket or tools._get_ticket
    started = []
    for tid in tracked_tickets():
        t = fetch(tid)
        if not t or t.get("status") != "closed" or not t.get("closed_at"):
            continue
        if _seen(tid) == t["closed_at"]:
            continue
        _mark(tid, t["closed_at"])
        if get_conn().execute("SELECT 1 FROM approvals WHERE ticket_id=? AND status='pending'", (tid,)).fetchone():
            continue
        notify(tid, CLOSED_NOTICE)
        agent.run_in_background(agent.start_run(tid))
        started.append(tid)
    return started


def watch_loop() -> None:
    while True:
        time.sleep(config.WATCH_INTERVAL)
        try:
            tick()
        except Exception as exc:   # the watcher must outlive an Engine restart or a bad row
            log.warning("watcher pass failed: %s", type(exc).__name__)


def start_watcher() -> None:
    if config.WATCH_INTERVAL > 0:
        threading.Thread(target=watch_loop, daemon=True, name="case-watcher").start()


def close_for_demo(ticket_id: str) -> dict:
    """Admin button: stand in for the city closing a website request."""
    r = httpx.post(f"{config.ENGINE_URL}/muni/tickets/{ticket_id}/close", headers=_engine_headers(), timeout=10)
    if r.status_code == 409:
        raise ValueError("this request is not open")
    r.raise_for_status()
    return r.json()
