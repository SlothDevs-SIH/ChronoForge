"""One regression test per bug found in the backend review (see the review notes in AYUSH_TASKS.md)."""
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app import agent, approvals, audit, citizen, config, photo, telegram
from app.db import get_conn
from app.main import app
from tests.test_core import ticket_with
from tests.test_photo import make_img

client = TestClient(app)


# --- bot replies were seconds late -----------------------------------------------------------------------------
def test_telegram_calls_share_one_kept_alive_client():
    assert telegram._http() is telegram._http()


def test_reply_path_makes_no_extra_round_trips(monkeypatch):
    calls = []
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setattr(telegram, "_api", lambda m, **p: calls.append(m) or {"ok": True})
    telegram.register_contact("t1", 5)
    telegram.send_request("t1", "pothole", "x", "y")
    calls.clear()
    telegram.handle_update({"callback_query": {"id": "c", "data": "ans:t1:2",
                                               "message": {"message_id": 1, "chat": {"id": 5}}}})
    time.sleep(0.2)   # the button clean-up runs in the background after the answer
    assert calls[0] == "answerCallbackQuery" and calls[1] == "sendMessage"   # spinner off, then the answer
    assert "sendChatAction" not in calls


# --- a button answered the wrong ticket / an old button re-answered a closed question -------------------------------
def test_button_applies_only_to_its_own_ticket(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    telegram.register_contact("old", 9)
    telegram.send_request("old", "pothole", "x", "y", sender=lambda c, t: None)
    telegram.handle_update({"message": {"chat": {"id": 9}, "text": "1"}})          # answers "old"
    telegram.register_contact("new", 9)
    telegram.send_request("new", "pothole", "x", "y", sender=lambda c, t: None)
    tap_old = {"callback_query": {"id": "c", "data": "ans:old:2", "message": {"message_id": 1, "chat": {"id": 9}}}}
    assert telegram.handle_update(tap_old) is None                                   # stale button: ignored
    assert telegram.get_request("new")["status"] == "asked"                          # "new" is untouched
    tap_new = {"callback_query": {"id": "c", "data": "ans:new:2", "message": {"message_id": 2, "chat": {"id": 9}}}}
    assert telegram.handle_update(tap_new).ticket_id == "new"


# --- "no problem, fixed" was read as NOT fixed -----------------------------------------------------------------
@pytest.mark.parametrize("text,intent", [
    ("no problem, fixed", "yes"), ("it is fixed, no issues", "yes"), ("all good", "yes"),
    ("not fixed yet", "no"), ("still broken", "no"), ("same as before", "no"), ("worse than before", "no"),
    ("yes but not fully", "partly"), ("half done", "partly"), ("abhi bhi waisa hi hai", "no"),
])
def test_everyday_phrases_are_read_correctly(text, intent):
    assert citizen.parse_intent(text) == intent


# --- duplicate approvals from re-runs ---------------------------------------------------------------------------
def test_rerun_refreshes_the_pending_approval_instead_of_duplicating():
    tid = ticket_with(True)
    agent.execute(agent.start_run(tid), delay=0)
    agent.execute(agent.start_run(tid), delay=0)
    pending = approvals.list_approvals("pending")
    assert len(pending) == 1
    assert any(e["event"]["type"] == "approval_refreshed" for e in audit.entries(500))


def test_failed_municipal_action_is_recorded_and_starts_no_outcome_clock(monkeypatch):
    monkeypatch.setattr(config, "OUTCOME_CHECK_DELAY", 5)
    started = []
    monkeypatch.setattr(approvals.threading, "Timer", lambda *a, **k: started.append(1) or type("T", (), {"start": lambda s: None})())
    agent.execute(agent.start_run(ticket_with(True)), delay=0)      # engine is down in tests
    done = approvals.decide(approvals.list_approvals()[0]["approval_id"], "approve")
    assert done["status"] == "approved" and done["engine_result"]["ok"] is False
    assert not started and any(e["event"]["type"] == "action_failed" for e in audit.entries(500))


# --- lost photo hashes between concurrent runs ---------------------------------------------------------------------
def test_photo_index_does_not_lose_entries_between_instances(tmp_path):
    path = str(tmp_path / "idx.json")
    a, b = photo.PhotoIndex(path), photo.PhotoIndex(path)          # two runs, each holding its own copy
    a.add("t1", {"phash": "a" * 16, "dhash": "a" * 16})
    b.add("t2", {"phash": "b" * 16, "dhash": "b" * 16})
    assert set(photo.PhotoIndex(path).data) == {"t1", "t2"}


def test_photo_index_survives_concurrent_writers(tmp_path):
    path = str(tmp_path / "idx.json")
    threads = [threading.Thread(target=lambda i=i: photo.PhotoIndex(path).add(f"t{i}", {"phash": f"{i:016x}", "dhash": "0" * 16}))
               for i in range(30)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(photo.PhotoIndex(path).data) == 30


# --- the API accepted any file path or internal URL as a "photo" --------------------------------------------------
def test_api_refuses_files_outside_the_photo_folders(tmp_path):
    outside = make_img(tmp_path / "x.jpg", 1)
    r = client.post("/evidence/photo", json={"ticket_id": "t", "closure_photo_url": outside})
    assert r.status_code == 403
    assert client.post("/evidence/photo", json={"ticket_id": "t", "closure_photo_url": "C:/Windows/win.ini"}).status_code == 403


def test_api_refuses_internal_urls():
    for url in ("http://127.0.0.1:8001/health", "http://localhost/x.jpg", "http://169.254.169.254/latest"):
        assert client.post("/evidence/photo", json={"ticket_id": "t", "closure_photo_url": url}).status_code == 403


# --- anyone could make the bot message arbitrary chats or approve reopens --------------------------------------
def test_admin_token_protects_messaging_and_approval_endpoints(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "s3cret")
    body = {"chat_id": "1", "lang": "en"}
    assert client.post("/citizen/t1/contact", json=body).status_code == 403
    assert client.post("/citizen/t1/contact", json=body, headers={"X-Admin-Token": "s3cret"}).status_code == 200
    assert client.post("/approvals/x/decide", json={"decision": "reject"}).status_code == 403
    assert client.post("/citizen/send", json={"ticket_id": "t1"}).status_code == 403


def test_open_when_no_admin_token_is_configured():
    assert client.post("/citizen/t1/contact", json={"chat_id": "1"}).status_code == 200


# --- stream 404 after a restart -------------------------------------------------------------------------------
def test_finished_run_can_still_be_streamed_after_it_left_memory():
    run_id = agent.start_run(ticket_with(True))
    agent.execute(run_id, delay=0)
    agent.RUNS.pop(run_id)                                  # as after a service restart
    with client.stream("GET", f"/agent/stream/{run_id}") as r:
        body = "".join(r.iter_lines())
    assert "event: trace" in body and "event: end" in body


def test_run_memory_is_bounded(monkeypatch):
    monkeypatch.setattr(agent, "MAX_RUNS_IN_MEMORY", 5)
    for i in range(12):
        agent.execute(agent.start_run(f"X-{i}"), delay=0)
    assert len(agent.RUNS) <= 6


# --- Telegram offset persists, so a restart cannot replay old taps ------------------------------------------------
def test_offset_is_saved_and_reloaded():
    from app import main
    main._save_offset(1234)
    assert main._load_offset() == 1234
    main._save_offset(1300)
    assert main._load_offset() == 1300


# --- two open questions in one chat made a typed reply ambiguous ---------------------------------------------------
def test_only_one_question_is_open_per_chat(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    for tid in ("q1", "q2"):
        telegram.register_contact(tid, 42)
        telegram.send_request(tid, "pothole", "x", "y", sender=lambda c, t: None)
    assert telegram.get_request("q1")["status"] == "superseded" and telegram.get_request("q2")["status"] == "asked"
    ev = telegram.handle_update({"message": {"chat": {"id": 42}, "text": "2"}})        # typed: unambiguous
    assert ev.ticket_id == "q2"
    old_button = {"callback_query": {"id": "c", "data": "ans:q1:1", "message": {"message_id": 1, "chat": {"id": 42}}}}
    assert telegram.handle_update(old_button) is None and telegram.get_request("q1")["status"] == "superseded"
    assert any(e["event"]["type"] == "citizen_question_superseded" for e in audit.entries(200))


def test_a_new_question_in_another_chat_does_not_withdraw_this_one():
    telegram.register_contact("a", 1)
    telegram.send_request("a", "pothole", "x", "y", sender=lambda c, t: None)
    telegram.register_contact("b", 2)
    telegram.send_request("b", "pothole", "x", "y", sender=lambda c, t: None)
    assert telegram.get_request("a")["status"] == "asked" and telegram.get_request("b")["status"] == "asked"
