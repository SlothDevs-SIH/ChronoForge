"""Website requests and case tracking.

  submit        a signed-in citizen files a request -> a ticket in the Engine ("web" city) -> a one-time Telegram link
  link          the citizen taps the link, the bot links their chat to the ticket and confirms the submission
  watch         a background loop notices when the city closes a tracked ticket and starts a verification run
  verdict       the citizen is told what the checks found; a reopen is only ever PROPOSED, an admin decides
  silence       no answer after a day: one reminder; after two: the case goes to a person
  photos        a photo the citizen sends in the chat is stored for a person to review (it carries no weight by itself)

Nothing here reopens a ticket by itself. The verdict thresholds and likelihood ratios are the Agent's existing ones.
"""
import json
import io
import logging
import secrets
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import agent, approvals, citizen, config, events, outbox, ratelimit, telegram
from .db import get_conn, lock
from .models import now_iso

log = logging.getLogger(__name__)

SUBMITTED = ("✅ Your request {ticket_id} has been submitted successfully.\n\n"
             "When the city marks it as fixed, TrueClose will check that it was really fixed and message you here. "
             "If it was not, an administrator can have it reopened.")
CLOSED_NOTICE = ("🔔 The city marked your request {ticket_id} as closed. TrueClose is now checking that the work was "
                 "really done, and may ask you a question here.")
REOPENED = ("🔁 Your request {ticket_id} has been reopened. An administrator reviewed the evidence and agreed it was "
            "not properly fixed.")
VERIFIED_FIXED = "✅ Good news: independent checks support that request {ticket_id} was really fixed."
NOT_FIXED = ("⚠️ Our checks suggest request {ticket_id} may not be properly fixed. An administrator is reviewing it. "
             "You will be told here if it is reopened.")
REMINDER = ("⏰ Reminder: we are still waiting for your answer about request {ticket_id}. Was it fixed? "
            "Tap a button below. It takes five seconds.")
ESCALATED = ("Thank you. We have not heard back about request {ticket_id}, so a person at TrueClose will look into it. "
             "You can still answer here at any time.")
PHOTO_RECEIVED = ("📷 Photo received for request {ticket_id}. A person will review it. A photo does not decide the case "
                  "by itself, so please also tap Yes, No or Partly if you have not already.")
NO_REQUEST_FOR_PHOTO = "I cannot match this photo to a request yet. Open your request on the TrueClose website and tap Connect Telegram."
BAD_LINK = "This link has expired or was already used. Open your request on the TrueClose website to get a new one."

_bot_username: str | None = None
DUP_HAMMING = 6   # same near-duplicate rule the closure-photo check uses


def engine_headers() -> dict:
    """How the Agent identifies itself to the Engine (shared service secret, when one is configured)."""
    return {"X-Service-Token": config.ENGINE_SERVICE_TOKEN} if config.ENGINE_SERVICE_TOKEN else {}


def bot_username() -> str | None:
    global _bot_username
    if _bot_username is None and config.TELEGRAM_BOT_TOKEN:
        try:
            _bot_username = telegram._api("getMe")["result"]["username"]
        except Exception as exc:
            log.warning("could not read the bot name from Telegram: %s", type(exc).__name__)
            return None
    return _bot_username


# ---- submit and link -------------------------------------------------------------------------------------------
def submit(user_id: str, category: str, text: str, ward: str, lat: float | None, lng: float | None) -> dict:
    """Create the ticket in the Engine and attach it to the citizen. Raises ValueError with a message for the user."""
    text = " ".join(text.split())
    if get_conn().execute("SELECT 1 FROM case_events e JOIN user_tickets u ON u.ticket_id=e.ticket_id "
                          "WHERE u.user_id=? AND e.kind='submitted' AND e.text=? AND e.ts > ?",
                          (user_id, f"Request filed: {text[:200]}", _ago(60))).fetchone():
        raise ValueError("you just sent this exact request, wait a minute before sending it again")
    try:
        r = httpx.post(f"{config.ENGINE_URL}/requests", headers=engine_headers(), timeout=10,
                       json={"category": category, "text": text, "ward": ward, "lat": lat, "lng": lng})
    except httpx.HTTPError:
        raise ConnectionError("the request service is not reachable right now, try again in a moment")
    if r.status_code in (422, 400):
        raise ValueError("describe the problem in a few words and pick a category")
    r.raise_for_status()
    ticket = r.json()
    link_ticket(user_id, ticket["ticket_id"])
    events.record(ticket["ticket_id"], "submitted", f"Request filed: {text[:200]}")
    return {"ticket": ticket, **new_link(ticket["ticket_id"])}


def link_ticket(user_id: str, ticket_id: str) -> None:
    """Make a request visible to the citizen who filed it (the same link an admin would make)."""
    with lock():
        get_conn().execute("DELETE FROM user_tickets WHERE user_id=? AND ticket_id=?", (user_id, ticket_id))
        get_conn().execute("INSERT INTO user_tickets (user_id, ticket_id, linked_by, created_at) VALUES (?,?,?,?)",
                           (user_id, ticket_id, user_id, now_iso()))
        get_conn().commit()


def _ago(seconds: float) -> str:
    return datetime.fromtimestamp(time.time() - seconds, timezone.utc).isoformat()


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
    events.record(ticket_id, "telegram_linked", "Telegram connected. Updates will arrive in the chat.")
    outbox.send(ticket_id, "telegram", chat_id, SUBMITTED.format(ticket_id=ticket_id))
    return ticket_id


def notify(ticket_id: str, template: str, buttons=None) -> bool:
    row = telegram.get_request(ticket_id)
    if row is None or row["status"] == "opted_out":
        return False
    return outbox.send(ticket_id, row["channel"], row["chat_id"], template.format(ticket_id=ticket_id), buttons)


# ---- language --------------------------------------------------------------------------------------------------
def follow_language(chat_id, text: str) -> None:
    """Answer in the language the citizen writes in. Only a clear signal changes it."""
    from . import lang
    found = lang.detect(text)
    if found is None or found == telegram._lang_for(chat_id):
        return
    with lock():
        get_conn().execute("UPDATE citizen_requests SET lang=? WHERE chat_id=? AND channel='telegram'", (found, str(chat_id)))
        get_conn().commit()


# ---- photos ----------------------------------------------------------------------------------------------------
def _open_ticket_for_chat(chat_id):
    return get_conn().execute(
        "SELECT * FROM citizen_requests WHERE chat_id=? AND channel='telegram' AND status!='opted_out' "
        "ORDER BY (status='asked') DESC, created_at DESC LIMIT 1", (str(chat_id),)).fetchone()


def receive_photo(chat_id, image: dict, fetch=None) -> dict | None:
    """Store a photo the citizen sent, with what can be told about it, and say so in the chat. It is evidence for a
    person to look at: it never moves the verdict, because nothing proves it shows the problem or the right place."""
    row = _open_ticket_for_chat(chat_id)
    if row is None:
        telegram._notify("telegram", chat_id, NO_REQUEST_FOR_PHOTO)
        return None
    ticket_id = row["ticket_id"]
    if config.RATE_LIMITS_ENABLED and not ratelimit.allow(f"photo:{chat_id}", 10, 3600):
        telegram._notify("telegram", chat_id, "You have sent many photos in the last hour. Please wait a little before sending more.")
        return None
    try:
        if image["size"] > config.MAX_PHOTO_BYTES:
            raise ValueError("too large")
        raw = (fetch or (lambda: telegram.download_file(image["file_id"])))()
        info = _analyse_and_store(ticket_id, row["chat_hash"], raw, image["source"])
    except Exception as exc:
        log.warning("photo not stored: %s", type(exc).__name__)
        telegram._notify("telegram", chat_id, "I could not read that photo. Please send it again as a normal picture (JPEG or PNG, under 8 MB).")
        return None
    events.record(ticket_id, "photo_received", "Photo received from the citizen" + (" (to be reviewed by a person)." if not info["flags"] else
                  f" (flagged for review: {', '.join(info['flags'])})."))
    telegram._notify("telegram", chat_id, PHOTO_RECEIVED.format(ticket_id=ticket_id))
    return info


def _analyse_and_store(ticket_id: str, chat_hash: str, raw: bytes, source: str) -> dict:
    from PIL import Image
    from . import photo as photo_mod
    img = Image.open(io.BytesIO(raw))
    img.verify()
    img = Image.open(io.BytesIO(raw))   # verify() leaves the file unusable
    if img.format not in ("JPEG", "PNG", "WEBP"):
        raise ValueError("unsupported image type")
    exif = photo_mod.exif_info(img)
    ph = photo_mod.hashes(img)["phash"]
    flags: list[str] = []
    details: dict = {"source": source, "has_gps": exif["lat"] is not None, "has_time": exif["taken_at"] is not None}
    from . import tools
    ticket = tools._get_ticket(ticket_id) or {}
    if exif["lat"] is not None and ticket.get("lat") is not None:
        metres = photo_mod.haversine_m(exif["lat"], exif["lng"], ticket["lat"], ticket["lng"])
        details["distance_m"] = round(metres, 1)
        if metres > photo_mod.GPS_FAR_METRES:
            flags.append("taken far from the reported place")
    import imagehash
    h = imagehash.hex_to_hash(ph)
    for r in get_conn().execute("SELECT ticket_id, phash FROM case_photos").fetchall():
        if int(h - imagehash.hex_to_hash(r["phash"])) <= DUP_HAMMING:
            if r["ticket_id"] != ticket_id:
                flags.append("same photo already used on another request")
                details["duplicate_of"] = r["ticket_id"]
            else:
                flags.append("same photo already sent on this request")
            break
    other, dist = photo_mod.PhotoIndex().nearest_other(ticket_id, ph)
    if dist is not None and dist <= DUP_HAMMING:
        flags.append("matches a city closure photo")
        details["matches_closure_photo_of"] = other
    details["flags"] = flags
    photo_id = uuid.uuid4().hex
    out = Path(config.PHOTO_DIR)
    out.mkdir(parents=True, exist_ok=True)
    clean = img.convert("RGB")
    clean.thumbnail((1280, 1280))
    path = out / f"{photo_id}.jpg"
    clean.save(path, "JPEG", quality=85)   # a fresh file: EXIF (GPS, device) is not kept
    with lock():
        get_conn().execute("INSERT INTO case_photos VALUES (?,?,?,?,?,?,?)",
                           (photo_id, ticket_id, chat_hash, ph, str(path), json.dumps(details), now_iso()))
        get_conn().commit()
    return {"photo_id": photo_id, "flags": flags, "details": details}


def photos_for(ticket_id: str) -> list[dict]:
    """Staff view: each photo as a small data URL with its review notes."""
    import base64
    out = []
    for r in get_conn().execute("SELECT * FROM case_photos WHERE ticket_id=? ORDER BY created_at", (ticket_id,)).fetchall():
        try:
            data = Path(r["path"]).read_bytes()
        except OSError:
            continue
        out.append({"photo_id": r["photo_id"], "received_at": r["created_at"], "details": json.loads(r["details"]),
                    "data_url": "data:image/jpeg;base64," + base64.b64encode(data).decode()})
    return out


# ---- verdicts --------------------------------------------------------------------------------------------------
def on_verdict(ticket_id: str, verdict) -> None:
    """Called when a verification run ends. Records it, and tells the citizen once per change of conclusion."""
    state = verdict.state
    text = {"verified_fixed": "Checks support that the work was really done.",
            "likely_not_fixed": "Checks suggest the work was not properly done. Waiting for an administrator.",
            "cannot_tell": "Checks were not conclusive. A person may look at it."}[state]
    events.record(ticket_id, f"verdict_{state}", text)
    if state == "cannot_tell":
        return
    last = get_conn().execute("SELECT v FROM kv WHERE k=?", (f"verdictmsg:{ticket_id}",)).fetchone()
    if last and last["v"] == state:
        return
    with lock():
        get_conn().execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (f"verdictmsg:{ticket_id}", state))
        get_conn().commit()
    notify(ticket_id, VERIFIED_FIXED if state == "verified_fixed" else NOT_FIXED)


# ---- watcher ---------------------------------------------------------------------------------------------------
def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def tracked_tickets() -> dict[str, str]:
    """ticket id -> when tracking began. Only a closure that happens AFTER this starts a verification on its own."""
    conn = get_conn()
    since: dict[str, str] = {}
    for r in conn.execute("SELECT ticket_id, created_at AS ts FROM user_tickets UNION ALL "
                          "SELECT ticket_id, created_at FROM citizen_requests WHERE status!='opted_out'"):
        if r["ticket_id"] not in since or _parse(r["ts"]) < _parse(since[r["ticket_id"]]):
            since[r["ticket_id"]] = r["ts"]
    return since


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
    tracked = tracked_tickets()

    def safe(tid):
        try:
            return fetch(tid)
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:   # one slow ticket must not hold up the rest
        fetched = dict(zip(tracked, pool.map(safe, tracked)))
    for tid, since in tracked.items():
        t = fetched[tid]
        if not t or t.get("status") != "closed" or not t.get("closed_at"):
            continue
        if _seen(tid) == t["closed_at"] or _parse(t["closed_at"]) < _parse(since):
            continue   # already handled, or closed before we started tracking (an old closure is not news)
        _mark(tid, t["closed_at"])
        if get_conn().execute("SELECT 1 FROM approvals WHERE ticket_id=? AND status='pending'", (tid,)).fetchone():
            continue
        events.record(tid, "closed", "The city marked the request as closed.")
        notify(tid, CLOSED_NOTICE)
        events.record(tid, "verification_started", "TrueClose started checking whether it was really fixed.")
        agent.run_in_background(agent.start_run(tid))
        started.append(tid)
    return started


def tick_silence(now: float | None = None) -> list[str]:
    """Reminder after REMINDER_HOURS without an answer, then one escalation to a person after ESCALATE_HOURS."""
    now = time.time() if now is None else now
    acted = []
    for r in get_conn().execute("SELECT * FROM citizen_requests WHERE status='asked' AND asked_at IS NOT NULL").fetchall():
        tid, age_h = r["ticket_id"], (now - _parse(r["asked_at"]).timestamp()) / 3600
        if age_h >= config.ESCALATE_HOURS:
            key = f"escalated:{tid}:{r['asked_at']}"
            if get_conn().execute("SELECT 1 FROM kv WHERE k=?", (key,)).fetchone():
                continue
            _escalate(tid, key)
            acted.append(tid)
        elif age_h >= config.REMINDER_HOURS:
            key = f"reminded:{tid}:{r['asked_at']}"
            if get_conn().execute("SELECT 1 FROM kv WHERE k=?", (key,)).fetchone():
                continue
            with lock():
                get_conn().execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (key, "1"))
                get_conn().commit()
            events.record(tid, "reminder_sent", "A reminder was sent because there was no answer yet.")
            notify(tid, REMINDER, telegram.answer_buttons(tid, r["lang"]))
            acted.append(tid)
    return acted


def _escalate(ticket_id: str, key: str) -> None:
    from .models import Evidence
    with lock():
        get_conn().execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (key, "1"))
        get_conn().commit()
    ev = citizen.silence_evidence(ticket_id)
    with lock():   # run_id NULL = on file for the next run, like an answered question
        get_conn().execute("INSERT INTO evidence VALUES (?,?,?,?,?)", (ev.evidence_id, ticket_id, None, ev.model_dump_json(), ev.created_at))
        get_conn().commit()
    events.record(ticket_id, "silence_escalated", "No answer from the citizen, so the case was sent to a person to review.")
    notify(ticket_id, ESCALATED)
    run_id = agent.start_run(ticket_id)
    verdict = agent.execute(run_id, delay=0)
    if verdict.state == "cannot_tell":   # nothing decisive: a person must look, so it shows on the Approvals page
        approvals.propose_action(ticket_id, run_id, "escalate", verdict)


def watch_loop() -> None:
    while True:
        time.sleep(config.WATCH_INTERVAL)
        for step in (tick, tick_silence, outbox.process_due):
            began = time.monotonic()
            try:
                step()
            except Exception as exc:   # one failing step must not stop the others, or the watcher
                log.warning("watcher step %s failed: %s", step.__name__, type(exc).__name__)
            if time.monotonic() - began > 5:
                log.warning("watcher step %s was slow: %.1f s", step.__name__, time.monotonic() - began)


def start_watcher() -> None:
    if config.WATCH_INTERVAL > 0:
        threading.Thread(target=watch_loop, daemon=True, name="case-watcher").start()


def close_for_demo(ticket_id: str) -> dict:
    """Admin button: stand in for the city closing a website request."""
    r = httpx.post(f"{config.ENGINE_URL}/muni/tickets/{ticket_id}/close", headers=engine_headers(), timeout=10)
    if r.status_code == 409:
        raise ValueError("this request is not open")
    r.raise_for_status()
    return r.json()
