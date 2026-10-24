import pytest

from app import citizen, config, telegram


@pytest.fixture
def sent(monkeypatch):
    """Capture every Telegram API call the bot makes."""
    calls = []
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setattr(telegram, "_api", lambda method, **p: calls.append((method, p)) or {"ok": True})
    return calls


def messages(calls):
    return [p for m, p in calls if m == "sendMessage"]


def start(ticket="t1", chat=5, lang="en"):
    telegram.register_contact(ticket, chat, lang)
    assert telegram.send_request(ticket, "pothole", "MG Road", "20 Oct")


def test_question_is_spaced_out_and_has_tap_buttons(sent):
    start()
    msg = messages(sent)[0]
    assert "\n\n" in msg["text"] and "1️⃣" in msg["text"] and "2️⃣" in msg["text"] and "STOP" in msg["text"]
    row = msg["reply_markup"]["inline_keyboard"][0]
    assert [b["callback_data"] for b in row] == ["ans:t1:1", "ans:t1:2", "ans:t1:3"]
    assert len(row) == 3 and all(len(b["callback_data"]) <= 64 for b in row)


def test_typed_reply_gets_an_acknowledgement(sent):
    start()
    sent.clear()
    ev = telegram.handle_update({"message": {"chat": {"id": 5}, "text": "2"}})
    assert ev.verdict == "contradicts_fix"
    reply = messages(sent)[-1]["text"]
    assert "NOT fixed" in reply and "\n\n" in reply
    assert any(m == "sendChatAction" for m, _ in sent)


def test_button_tap_is_recorded_and_the_buttons_are_removed(sent):
    start()
    sent.clear()
    tap = {"callback_query": {"id": "cb1", "data": "ans:t1:1",
                              "message": {"message_id": 9, "chat": {"id": 5}}}}
    ev = telegram.handle_update(tap)
    assert ev.verdict == "supports_fix"
    methods = [m for m, _ in sent]
    assert "answerCallbackQuery" in methods and "editMessageReplyMarkup" in methods
    assert "fixed" in messages(sent)[-1]["text"].lower()


def test_unclear_reply_keeps_the_question_open_and_reasks(sent):
    start()
    sent.clear()
    assert telegram.handle_update({"message": {"chat": {"id": 5}, "text": "hmm what"}}) is None
    assert telegram.get_request("t1")["status"] == "asked"          # still waiting for a real answer
    again = messages(sent)[-1]
    assert "did not understand" in again["text"] and "inline_keyboard" in again["reply_markup"]
    assert telegram.handle_update({"message": {"chat": {"id": 5}, "text": "nahi"}}).verdict == "contradicts_fix"
    assert telegram.get_request("t1")["status"] == "answered"


def test_photo_only_reply_is_acknowledged_and_question_stays_open(sent):
    start()
    sent.clear()
    assert telegram.handle_update({"message": {"chat": {"id": 5}, "photo": [{"file_id": "f"}]}}) is None
    assert "photo" in messages(sent)[-1]["text"].lower()
    assert telegram.get_request("t1")["status"] == "asked"


def test_start_help_and_idle_messages(sent):
    telegram.handle_update({"message": {"chat": {"id": 77}, "text": "/start"}})
    telegram.handle_update({"message": {"chat": {"id": 77}, "text": "/help"}})
    telegram.handle_update({"message": {"chat": {"id": 77}, "text": "random"}})   # nothing open for this chat
    texts = [m["text"] for m in messages(sent)]
    assert len(texts) == 3 and "How this works" in texts[1] and "no open question" in texts[2]


def test_stop_is_confirmed_in_the_citizens_language(sent):
    start(lang="hi")
    sent.clear()
    telegram.handle_update({"message": {"chat": {"id": 5}, "text": "STOP"}})
    assert "सूची से हटा" in messages(sent)[-1]["text"] and not telegram.has_contact("t1")


def test_a_failing_acknowledgement_never_loses_the_evidence(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "tok")
    calls = {"n": 0}

    def flaky(method, **p):
        calls["n"] += 1
        if calls["n"] > 1:                     # the question goes out, every later call fails
            raise ConnectionError
        return {"ok": True}
    monkeypatch.setattr(telegram, "_api", flaky)
    start()
    ev = telegram.handle_update({"message": {"chat": {"id": 5}, "text": "2"}})
    assert ev is not None and telegram.get_request("t1")["status"] == "answered"


@pytest.mark.parametrize("lang", ["en", "hi", "mr", "kn"])
def test_every_language_has_every_message(lang):
    for kind in ("yes", "no", "partly", "photo", "unclear", "stop", "idle", "help"):
        assert citizen.ack_text(lang, kind).strip()
    assert len(citizen.button_labels(lang)) == 3 and "\n\n" in citizen.build_prompt(lang, "x", "y", "z")


def test_a_fix_is_never_confirmed_without_the_photo_check():
    """Regression: one citizen 'Yes' pushed the posterior under 0.25 and cleared a ticket with a bad photo."""
    from app import agent, tools
    from app.models import Evidence, Score
    calls = []

    def photo(tid, url=None):
        calls.append("photo")
        return Evidence(ticket_id=tid, check="photo", verdict="contradicts_fix", likelihood_ratio=8.0,
                        confidence=0.9, cost=1, details={"flags": ["duplicate"]})
    tools_get = tools.get_score
    tools.get_score = lambda tid: (Score(ticket_id=tid, p_false_closure=0.5, eligible_checks=["photo", "citizen"],
                                         satellite_eligible=False), "test")
    original = (tools.check_photo, tools.ask_citizen)
    tools.check_photo = photo
    tools.ask_citizen = lambda tid: Evidence(ticket_id=tid, check="citizen", verdict="supports_fix",
                                             likelihood_ratio=0.1, confidence=0.9, cost=2)
    try:
        run_id = agent.start_run("T-gate")
        v = agent.execute(run_id, planner=lambda s: ("ask_citizen", "ask first"), delay=0)
    finally:
        tools.get_score, (tools.check_photo, tools.ask_citizen) = tools_get, original
    assert calls == ["photo"]                                   # the gate forced the photo check
    assert v.state != "verified_fixed"                          # and the bad photo stopped a false confirmation
    assert any("never confirmed" in e.summary for e in agent.RUNS[run_id].events)


def test_gate_is_skipped_when_the_photo_is_unaffordable_or_already_used():
    from app import agent, planner
    s = planner.PlanState(budget_left=0, satellite_eligible=False)
    assert not agent._photo_gate_open(0.1, s)
    s = planner.PlanState(budget_left=9, satellite_eligible=False, used={"check_photo"})
    assert not agent._photo_gate_open(0.1, s)
    assert agent._photo_gate_open(0.1, planner.PlanState(budget_left=9, satellite_eligible=False))
    assert not agent._photo_gate_open(0.5, planner.PlanState(budget_left=9, satellite_eligible=False))
