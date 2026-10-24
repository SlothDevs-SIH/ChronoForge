"""Website request -> Telegram link -> city closes -> watcher runs once -> admin reopens -> citizen told."""
from app import agent, approvals, cases, config, telegram
from app.db import get_conn
from app.models import Verdict

SENT = []


def _capture(monkeypatch):
    SENT.clear()
    def fake(channel, chat_id, text, buttons=None):
        SENT.append((str(chat_id), text))
        return True
    monkeypatch.setattr(telegram, "deliver", fake)


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
    cases.link_ticket("u1", "web-00001")
    telegram.register_contact("web-00001", 555)
    open_ = {"status": "open", "closed_at": None}
    from datetime import datetime, timedelta, timezone

    def later(h):
        return (datetime.now(timezone.utc) + timedelta(hours=h)).isoformat()
    closed = {"status": "closed", "closed_at": later(1)}
    assert cases.tick(lambda t: open_) == []
    assert cases.tick(lambda t: closed) == ["web-00001"]
    assert "closed" in SENT[-1][1]
    assert cases.tick(lambda t: closed) == []                         # same closure: not run again
    assert cases.tick(lambda t: {**closed, "closed_at": later(2)}) == ["web-00001"]               # a new closure is
    assert cases.tick(lambda t: {**closed, "closed_at": "2020-01-01T00:00:00Z"}) == []           # closed before tracking: not news


def test_reopen_is_only_announced_after_approval(monkeypatch):
    _capture(monkeypatch)
    telegram.register_contact("web-00001", 555)
    v = Verdict(ticket_id="web-00001", state="likely_not_fixed", posterior=0.9, prior=0.5, explanation="x", evidence_ids=[], recommended_action="reopen", requires_human=True)
    a = approvals.propose_action("web-00001", None, "reopen", v)
    assert SENT == []                                                 # proposing tells nobody
    monkeypatch.setattr(approvals, "_call_engine", lambda action, tid: {"ok": True, "response": {}})
    approvals.decide(a["approval_id"], "approve")
    assert "reopened" in SENT[-1][1]
    from app import events
    assert [e["kind"] for e in events.timeline("web-00001", staff=False)] == ["reopened"]   # the citizen's history shows it too


def test_failed_reopen_does_not_tell_the_citizen(monkeypatch):
    _capture(monkeypatch)
    telegram.register_contact("web-00001", 555)
    v = Verdict(ticket_id="web-00001", state="likely_not_fixed", posterior=0.9, prior=0.5, explanation="x", evidence_ids=[], recommended_action="reopen", requires_human=True)
    a = approvals.propose_action("web-00001", None, "reopen", v)
    monkeypatch.setattr(approvals, "_call_engine", lambda action, tid: {"ok": False, "error": "down"})
    approvals.decide(a["approval_id"], "approve")
    assert SENT == []
