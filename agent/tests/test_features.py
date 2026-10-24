"""Status updates, citizen photos, reasons for the admin, silence handling, language, delivery retries, limits, summary."""
import io
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import approvals, auth, cases, config, events, explain, lang, outbox, ratelimit, summary, telegram
from app.db import get_conn
from app.main import app
from app.models import Evidence, Verdict

client = TestClient(app)
SENT: list = []


@pytest.fixture(autouse=True)
def sent(monkeypatch):
    SENT.clear()

    def fake(channel, chat_id, text, buttons=None):
        SENT.append((str(chat_id), text, buttons))
        return True
    monkeypatch.setattr(telegram, "deliver", fake)


def verdict(state, tid="web-00001"):
    return Verdict(ticket_id=tid, state=state, prior=0.5, posterior=0.9 if state == "likely_not_fixed" else 0.1, evidence_ids=[],
                   recommended_action="reopen" if state == "likely_not_fixed" else "none", requires_human=True, explanation="x")


def jpeg(color=(200, 30, 30), size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", size, color)
    for x in range(0, size[0], 4):          # texture, so the perceptual hash is not that of a flat colour
        for y in range(0, size[1], 4):
            if (x * 7 + y * 13 + color[0]) % 5 < 2:
                img.putpixel((x, y), (255 - color[0], color[1], 255 - color[2]))
    img.save(buf, "JPEG")
    return buf.getvalue()


# ---- 1. status updates ----------------------------------------------------------------------------------------
def test_citizen_hears_each_conclusion_once():
    telegram.register_contact("web-00001", 9)
    cases.on_verdict("web-00001", verdict("verified_fixed"))
    cases.on_verdict("web-00001", verdict("verified_fixed"))                      # same conclusion: not repeated
    assert [s[1] for s in SENT] == [cases.VERIFIED_FIXED.format(ticket_id="web-00001")]
    cases.on_verdict("web-00001", verdict("likely_not_fixed"))                    # a changed conclusion is news
    assert "may not be properly fixed" in SENT[-1][1] and len(SENT) == 2
    cases.on_verdict("web-00001", verdict("cannot_tell"))                         # inconclusive: recorded, not announced
    assert len(SENT) == 2
    kinds = [e["kind"] for e in events.timeline("web-00001", staff=False)]
    assert kinds == ["verdict_verified_fixed", "verdict_verified_fixed", "verdict_likely_not_fixed", "verdict_cannot_tell"]


# ---- 2. citizen photos ------------------------------------------------------------------------------------------
def test_photo_is_stored_without_exif_and_never_changes_the_verdict():
    telegram.register_contact("web-00001", 9)
    info = cases.receive_photo(9, {"file_id": "f", "source": "photo", "size": 100}, fetch=lambda: jpeg())
    assert info and info["flags"] == []
    assert "Photo received" in SENT[-1][1]
    shown = cases.photos_for("web-00001")
    assert len(shown) == 1 and shown[0]["data_url"].startswith("data:image/jpeg;base64,")
    assert get_conn().execute("SELECT COUNT(*) AS n FROM evidence").fetchone()["n"] == 0     # no likelihood ratio, no evidence row
    assert any(e["kind"] == "photo_received" for e in events.timeline("web-00001", staff=False))


def test_same_photo_on_another_request_is_flagged_for_review():
    telegram.register_contact("web-00001", 9)
    telegram.register_contact("web-00002", 10)
    cases.receive_photo(9, {"file_id": "f", "source": "photo", "size": 1}, fetch=lambda: jpeg())
    info = cases.receive_photo(10, {"file_id": "f", "source": "photo", "size": 1}, fetch=lambda: jpeg())
    assert "same photo already used on another request" in info["flags"] and info["details"]["duplicate_of"] == "web-00001"


def test_bad_or_oversized_photo_is_refused_politely():
    telegram.register_contact("web-00001", 9)
    assert cases.receive_photo(9, {"file_id": "f", "source": "photo", "size": 1}, fetch=lambda: b"not an image") is None
    assert "could not read" in SENT[-1][1]
    assert cases.receive_photo(9, {"file_id": "f", "source": "photo", "size": config.MAX_PHOTO_BYTES + 1}, fetch=lambda: jpeg()) is None
    assert cases.photos_for("web-00001") == []


def test_photo_from_an_unlinked_chat_is_not_attached_anywhere():
    assert cases.receive_photo(777, {"file_id": "f", "source": "photo", "size": 1}, fetch=lambda: jpeg()) is None
    assert "cannot match" in SENT[-1][1]


def test_photo_message_in_the_bot_does_not_answer_the_question(monkeypatch):
    telegram.register_contact("web-00001", 9)
    seen = []
    monkeypatch.setattr(cases, "receive_photo", lambda chat, image: seen.append(image))
    out = telegram.handle_update({"message": {"chat": {"id": 9}, "photo": [{"file_id": "a", "file_size": 10}, {"file_id": "b", "file_size": 20}]}})
    assert out is None and seen[0]["file_id"] == "b" and seen[0]["source"] == "photo"
    telegram.handle_update({"message": {"chat": {"id": 9}, "document": {"file_id": "d", "mime_type": "image/png", "file_size": 5}}})
    assert seen[1]["source"] == "file"


# ---- 3. reasons for the admin ----------------------------------------------------------------------------------
def _evidence(**kw):
    ev = Evidence(ticket_id="web-00001", cost=1, confidence=0.7, **kw)
    get_conn().execute("INSERT INTO evidence VALUES (?,?,?,?,?)", (ev.evidence_id, "web-00001", None, ev.model_dump_json(), ev.created_at))
    get_conn().commit()
    return ev


def test_reasons_are_built_only_from_recorded_evidence():
    a = _evidence(check="citizen", verdict="contradicts_fix", likelihood_ratio=6, details={"intent": "no"})
    b = _evidence(check="photo", verdict="contradicts_fix", likelihood_ratio=8,
                  details={"flags": ["duplicate", "location"], "checks": {"duplicate": {"nearest_ticket": "mum-9"}, "location": {"distance_m": 842.0}}})
    c = _evidence(check="satellite", verdict="inconclusive", likelihood_ratio=1, details={})
    out = explain.for_verdict({"evidence_ids": [a.evidence_id, b.evidence_id, c.evidence_id], "prior": 0.5, "posterior": 0.93})
    assert "The citizen said it is not fixed." in out["against"]
    assert any("mum-9" in line for line in out["against"]) and any("842 m" in line for line in out["against"])
    assert out["for"] == [] and len(out["unknown"]) == 1 and "93%" in out["summary"]


def test_no_evidence_says_so_instead_of_inventing_reasons():
    out = explain.for_verdict({"evidence_ids": [], "prior": 0.5, "posterior": 0.5})
    assert out["against"] == [] and out["for"] == [] and "No independent check" in out["unknown"][0]


def test_approvals_endpoint_carries_the_reasons():
    ev = _evidence(check="citizen", verdict="contradicts_fix", likelihood_ratio=6, details={"intent": "partly"})
    v = verdict("likely_not_fixed").model_copy(update={"evidence_ids": [ev.evidence_id]})
    approvals.propose_action("web-00001", None, "reopen", v)
    got = client.get("/approvals").json()[0]
    assert got["explain"]["against"] == ["The citizen said it is only partly fixed."]


# ---- 4. silence ------------------------------------------------------------------------------------------------
def _asked(hours_ago, tid="web-00001", chat=9):
    telegram.register_contact(tid, chat)
    when = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    get_conn().execute("UPDATE citizen_requests SET status='asked', asked_at=? WHERE ticket_id=?", (when, tid))
    get_conn().commit()


def test_reminder_once_then_escalation_to_a_person(monkeypatch):
    from app import agent
    monkeypatch.setattr(agent, "execute", lambda run_id, **k: verdict("cannot_tell"))   # the stub tools would otherwise decide
    _asked(25)
    assert cases.tick_silence() == ["web-00001"]
    assert "Reminder" in SENT[-1][1] and SENT[-1][2]                  # with the answer buttons
    assert cases.tick_silence() == []                                  # one reminder only
    _asked(49)
    assert cases.tick_silence() == ["web-00001"]
    assert "person at TrueClose" in SENT[-1][1]
    pending = approvals.list_approvals("pending")
    assert [(p["action"], p["ticket_id"]) for p in pending] == [("escalate", "web-00001")]
    assert cases.tick_silence() == []                                  # escalated once
    kinds = [e["kind"] for e in events.timeline("web-00001", staff=True)]
    assert "reminder_sent" in kinds and "silence_escalated" in kinds


def test_a_recent_question_is_left_alone():
    _asked(2)
    assert cases.tick_silence() == [] and SENT == []


# ---- 5. language ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("नहीं, अभी भी ठीक नहीं हुआ है", "hi"), ("नाही, काम झाले नाही", "mr"), ("ಇಲ್ಲ ಇನ್ನೂ ಆಗಿಲ್ಲ", "kn"),
    ("it is still broken here", "en"), ("nahi", None), ("2", None), ("👍", None), ("ok", None)])
def test_language_detection(text, expected):
    assert lang.detect(text) == expected


def test_bot_follows_the_language_the_citizen_writes_in():
    telegram.register_contact("web-00001", 9)
    assert telegram._lang_for(9) == "en"
    cases.follow_language(9, "ಇಲ್ಲ ಇನ್ನೂ ಆಗಿಲ್ಲ")
    assert telegram._lang_for(9) == "kn"
    cases.follow_language(9, "2")                                      # a button number never switches language
    assert telegram._lang_for(9) == "kn"


# ---- 6. delivery retry ------------------------------------------------------------------------------------------
def test_failed_send_is_queued_and_retried_then_given_up_on(monkeypatch):
    calls = []

    def flaky(channel, chat_id, text, buttons=None):
        calls.append(text)
        raise httpx.ConnectError("down")
    monkeypatch.setattr(telegram, "deliver", flaky)
    assert outbox.send("web-00001", "telegram", 9, "hello") is True    # queued, not lost
    assert outbox.stats()["pending"] == 1
    assert outbox.process_due(time.time()) == 0                        # not due yet: no extra attempt
    for step in range(5):
        outbox.process_due(time.time() + 100000 * (step + 1))
    assert outbox.stats() == {"pending": 0, "sent": 0, "failed": 1}
    assert len(calls) == outbox.MAX_ATTEMPTS
    assert any(e["kind"] == "message_failed" for e in events.timeline("web-00001", staff=True))
    assert not any(e["kind"] == "message_failed" for e in events.timeline("web-00001", staff=False))


def test_queued_message_is_delivered_when_the_channel_recovers(monkeypatch):
    state = {"up": False}

    def sometimes(channel, chat_id, text, buttons=None):
        if not state["up"]:
            raise httpx.ConnectError("down")
        SENT.append((str(chat_id), text, buttons))
        return True
    monkeypatch.setattr(telegram, "deliver", sometimes)
    outbox.send(None, "telegram", 9, "hello", [[{"text": "Yes"}]])
    state["up"] = True
    assert outbox.process_due(time.time() + 1000) == 1
    assert SENT == [("9", "hello", [[{"text": "Yes"}]])] and outbox.stats()["sent"] == 1


def test_a_blocked_bot_is_not_retried(monkeypatch):
    def blocked(channel, chat_id, text, buttons=None):
        raise httpx.HTTPStatusError("blocked", request=httpx.Request("POST", "http://x"), response=httpx.Response(403))
    monkeypatch.setattr(telegram, "deliver", blocked)
    assert outbox.send(None, "telegram", 9, "hello") is False
    assert outbox.stats()["pending"] == 0


def test_unconfigured_channel_sends_nothing_and_queues_nothing(monkeypatch):
    monkeypatch.setattr(telegram, "deliver", lambda *a, **k: False)
    assert outbox.send(None, "telegram", 9, "hello") is False and outbox.stats()["pending"] == 0


# ---- 7. retry a reopen the city did not carry out ---------------------------------------------------------------
def test_failed_reopen_can_be_retried_and_the_citizen_is_told_only_on_success(monkeypatch):
    telegram.register_contact("web-00001", 9)
    a = approvals.propose_action("web-00001", None, "reopen", verdict("likely_not_fixed"))
    monkeypatch.setattr(approvals, "_call_engine", lambda action, tid: {"ok": False, "error": "down"})
    approvals.decide(a["approval_id"], "approve")
    assert SENT == []
    pending = approvals.propose_action("web-00002", None, "reopen", verdict("likely_not_fixed", "web-00002"))
    with pytest.raises(ValueError):
        approvals.retry(pending["approval_id"])                        # still pending: nothing to retry
    monkeypatch.setattr(approvals, "_call_engine", lambda action, tid: {"ok": True, "response": {}})
    done = approvals.retry(a["approval_id"])
    assert done["engine_result"]["ok"] and "reopened" in SENT[-1][1]
    with pytest.raises(ValueError):
        approvals.retry(a["approval_id"])                              # it worked, nothing left to retry


# ---- 8. limits ----------------------------------------------------------------------------------------------------
def test_login_is_rate_limited_per_client(monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT", True)
    ratelimit.reset()
    codes = [client.post("/auth/login", json={"email": "a@b.in", "password": "x" * 9}).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]
    ratelimit.reset()


def test_sliding_window_forgets_old_hits():
    ratelimit.reset()
    assert [ratelimit.allow("k", 2, 10, now=t) for t in (0, 1, 2)] == [True, True, False]
    assert ratelimit.allow("k", 2, 10, now=11.5) is True


def test_a_user_cannot_flood_requests(monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT", True)
    ratelimit.reset()
    from fastapi import HTTPException
    for _ in range(config.REQUESTS_PER_HOUR):
        ratelimit.check_user("request", "u1", config.REQUESTS_PER_HOUR, 3600)
    with pytest.raises(HTTPException) as e:
        ratelimit.check_user("request", "u1", config.REQUESTS_PER_HOUR, 3600)
    assert e.value.status_code == 429
    ratelimit.reset()


# ---- 9. summary ---------------------------------------------------------------------------------------------------
def test_summary_counts_the_timeline():
    for kind in ("submitted", "submitted", "closed", "verdict_likely_not_fixed", "verdict_verified_fixed", "reopened"):
        events.record("web-00001", kind, kind)
    s = summary.build(7)
    assert s["counts"]["submitted"] == 2 and s["not_fixed_rate"] == 0.5
    assert "2 requests filed" in s["text"] and "1 reopened" in s["text"]


def test_summary_with_nothing_has_no_rate():
    assert summary.build(7)["not_fixed_rate"] is None


# ---- 10. timelines and who can see what -------------------------------------------------------------------------
def _login(email, role="citizen"):
    config.AUTH_ENFORCE = True
    client.post("/auth/register", json={"email": email, "name": "T", "password": "longenough1", "role": role})
    return {"Authorization": "Bearer " + client.post("/auth/login", json={"email": email, "password": "longenough1"}).json()["token"]}


def test_citizen_sees_only_their_own_citizen_visible_events():
    me, other = _login("me@x.in"), _login("other@x.in")
    uid = client.get("/auth/me", headers=me).json()["user_id"]
    auth.add_ticket(uid, "web-00001")
    events.record("web-00001", "closed", "The city marked it closed.")
    events.record("web-00001", "reopen_proposed", "internal", "staff")
    got = client.get("/me/requests/web-00001/timeline", headers=me).json()
    assert [e["kind"] for e in got] == ["closed"]
    assert client.get("/me/requests/web-00001/timeline", headers=other).status_code == 404
    assert client.get("/cases/web-00001/timeline", headers=me).status_code == 403
    assert client.get("/cases/web-00001/photos", headers=me).status_code == 403
    assert client.get("/admin/summary", headers=me).status_code == 403
    assert client.post("/approvals/x/retry", headers=me).status_code == 403


def test_staff_see_internal_events_too():
    config.AUTH_ENFORCE = True
    config.FIRST_ADMIN_EMAIL, config.FIRST_ADMIN_PASSWORD = "a@x.in", "adminpass123"
    auth.seed_admin()
    admin = {"Authorization": "Bearer " + client.post("/auth/login", json={"email": "a@x.in", "password": "adminpass123"}).json()["token"]}
    events.record("web-00001", "reopen_proposed", "internal", "staff")
    assert [e["kind"] for e in client.get("/cases/web-00001/timeline", headers=admin).json()] == ["reopen_proposed"]
    assert client.get("/admin/summary?days=7", headers=admin).json()["days"] == 7


# ---- 11. deployment basics ----------------------------------------------------------------------------------------
def test_ready_reports_ok_with_stubs_and_503_when_the_engine_is_needed_but_down(monkeypatch):
    assert client.get("/ready").json()["ok"] is True
    monkeypatch.setattr(config, "USE_STUBS", False)
    assert client.get("/ready").status_code == 503


def test_similar_check_never_blocks_filing_when_the_engine_is_down():
    h = _login("c@x.in")
    assert client.get("/me/requests/similar?category=pothole&text=big+hole", headers=h).json() == []
