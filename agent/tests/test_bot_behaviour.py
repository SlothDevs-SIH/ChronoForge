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
