"""Website request -> Telegram link -> city closes -> watcher runs once -> admin reopens -> citizen told."""
from app import agent, approvals, auth, cases, config, telegram
from app.db import get_conn
from app.models import Verdict

SENT = []


def _capture(monkeypatch):
    SENT.clear()
    monkeypatch.setattr(telegram, "_notify", lambda channel, chat_id, text, buttons=None: SENT.append((str(chat_id), text)))


def _user():
    return auth.register("c@x.in", "C", "longenough1", "citizen")["user_id"]


def test_link_token_is_single_use_and_confirms_the_submission(monkeypatch):
    _capture(monkeypatch)
    cases.new_link("web-00001")
    token = get_conn().execute("SELECT k FROM kv WHERE k LIKE 'link:%'").fetchone()["k"][5:]
    assert cases.claim_link(token, 555) == "web-00001"
    assert "web-00001" in SENT[-1][1] and "submitted successfully" in SENT[-1][1]
    assert telegram.has_contact("web-00001")
    assert cases.claim_link(token, 777) is None                      # a second chat cannot reuse it


def test_start_deep_link_through_the_bot(monkeypatch):
    _capture(monkeypatch)
    cases.new_link("web-00002")
    token = get_conn().execute("SELECT k FROM kv WHERE k LIKE 'link:%'").fetchone()["k"][5:]
    telegram.handle_update({"message": {"chat": {"id": 42}, "text": f"/start {token}"}})
    assert telegram.has_contact("web-00002")
    telegram.handle_update({"message": {"chat": {"id": 43}, "text": "/start bogus"}})
    assert "expired" in SENT[-1][1]


def test_watcher_handles_each_closure_once_and_skips_open_approvals(monkeypatch):
    _capture(monkeypatch)
    started = []
    monkeypatch.setattr(agent, "start_run", lambda tid: started.append(tid) or "run")
    monkeypatch.setattr(agent, "run_in_background", lambda run_id: None)
    uid = _user()
    auth.add_ticket(uid, "web-00001")
    telegram.register_contact("web-00001", 555)
    open_ = {"status": "open", "closed_at": None}
    closed = {"status": "closed", "closed_at": "2026-10-24T10:00:00Z"}
    assert cases.tick(lambda t: open_) == []
    assert cases.tick(lambda t: closed) == ["web-00001"]
    assert "closed" in SENT[-1][1]
    assert cases.tick(lambda t: closed) == []                         # same closure: not run again
    assert cases.tick(lambda t: {**closed, "closed_at": "2026-10-25T10:00:00Z"}) == ["web-00001"]   # a new closure is


def test_reopen_is_only_announced_after_approval(monkeypatch):
    _capture(monkeypatch)
    telegram.register_contact("web-00001", 555)
    v = Verdict(ticket_id="web-00001", state="likely_not_fixed", posterior=0.9, prior=0.5, explanation="x", evidence_ids=[], recommended_action="reopen", requires_human=True)
    a = approvals.propose_action("web-00001", None, "reopen", v)
    assert SENT == []                                                 # proposing tells nobody
    monkeypatch.setattr(approvals, "_call_engine", lambda action, tid: {"ok": True, "response": {}})
    approvals.decide(a["approval_id"], "approve")
    assert "reopened" in SENT[-1][1]


def test_failed_reopen_does_not_tell_the_citizen(monkeypatch):
    _capture(monkeypatch)
    telegram.register_contact("web-00001", 555)
    v = Verdict(ticket_id="web-00001", state="likely_not_fixed", posterior=0.9, prior=0.5, explanation="x", evidence_ids=[], recommended_action="reopen", requires_human=True)
    a = approvals.propose_action("web-00001", None, "reopen", v)
    monkeypatch.setattr(approvals, "_call_engine", lambda action, tid: {"ok": False, "error": "down"})
    approvals.decide(a["approval_id"], "approve")
    assert SENT == []
