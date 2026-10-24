import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from app import agent, audit, clip_check, config, photo, telegram
from app.main import app


def update(chat_id, text):
    return {"message": {"chat": {"id": chat_id}, "text": text}}


def asked(ticket_id, chat_id, lang="en"):
    telegram.register_contact(ticket_id, chat_id, lang)
    telegram.send_request(ticket_id, "pothole", "MG Road", "20 Oct", sender=lambda c, t: None)


def test_send_then_reply_becomes_evidence():
    telegram.register_contact("t1", 555, "hi")
    sent = []
    assert telegram.send_request("t1", "pothole", "MG Road", "20 Oct", sender=lambda c, t: sent.append((c, t)))
    assert sent[0][0] == "555" and "STOP" in sent[0][1]
    ev = telegram.handle_update(update(555, "2"))
    assert ev.check == "citizen" and ev.verdict == "contradicts_fix" and ev.ticket_id == "t1"
    assert telegram.get_request("t1")["status"] == "answered"


def test_reply_without_open_request_is_ignored():
    telegram.register_contact("t1", 555)   # registered, never asked
    assert telegram.handle_update(update(555, "2")) is None
    assert telegram.handle_update(update(999, "2")) is None


def test_stop_opts_out_and_blocks_sending():
    asked("t1", 555)
    assert telegram.handle_update(update(555, "STOP")) is None
    assert not telegram.has_contact("t1")
    assert telegram.send_request("t1", "pothole", "x", "y", sender=lambda c, t: 1 / 0) is False


def test_audit_never_contains_raw_chat_id():
    asked("t1", 4242424242)
    telegram.handle_update(update(4242424242, "1"))
    assert "4242424242" not in str(audit.entries(100))
    assert audit.verify()["ok"]


def test_webhook_secret_and_rerun(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(config, "TELEGRAM_WEBHOOK_SECRET", "s3")
    assert client.post("/channels/telegram/webhook", json=update(1, "2")).status_code == 403
    asked("t1", 1)
    r = client.post("/channels/telegram/webhook", json=update(1, "2"),
                    headers={"X-Telegram-Bot-Api-Secret-Token": "s3"})
    assert r.status_code == 200 and "run_id" in r.json()


def test_stored_reply_is_used_by_next_run():
    asked("t1", 1)
    telegram.handle_update(update(1, "2"))
    run_id = agent.start_run("t1")
    agent.execute(run_id, delay=0)
    citizen_ev = [e for e in agent.RUNS[run_id].evidence if e.check == "citizen"]
    assert len(citizen_ev) == 1 and citizen_ev[0].details["intent"] == "no"


# CLIP, with a fake embedder so no model is downloaded
class FakeEmbedder:
    """image() is the mean colour direction; text() maps the 'problem' prompt to red, 'fixed' to green."""

    def image(self, img):
        v = np.array(img.convert("RGB").resize((1, 1)).getpixel((0, 0)), dtype=float)
        return v / (np.linalg.norm(v) or 1)

    def text(self, texts):
        return np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])


class BrokenEmbedder:
    def image(self, img):
        raise RuntimeError

    def text(self, texts):
        raise RuntimeError


def solid(color):
    return Image.new("RGB", (8, 8), color)


def test_scene_still_broken_flagged_and_fixed_scene_passes():
    f, p, d = clip_check.clip_checks(solid((255, 0, 0)), "pothole", emb=FakeEmbedder())
    assert f == ["scene"] and d["scene"]["p_problem_present"] > 0.9
    f, p, d = clip_check.clip_checks(solid((0, 255, 0)), "pothole", emb=FakeEmbedder())
    assert p == ["scene"] and not f


def test_before_after_different_place():
    f, _, _ = clip_check.clip_checks(solid((0, 255, 0)), "pothole", solid((255, 0, 0)), FakeEmbedder())
    assert "before_after" in f


def test_verify_photo_with_clip_flags_scene(tmp_path):
    path = tmp_path / "a.png"
    solid((255, 0, 0)).save(path)
    ev = photo.verify_photo("t", str(path), {"category": "pothole"}, photo.PhotoIndex(str(tmp_path / "i.json")),
                            use_clip=True, embedder=FakeEmbedder())
    assert ev.verdict == "contradicts_fix" and "scene" in ev.details["flags"] and ev.likelihood_ratio == 5.0


def test_clip_failure_degrades_to_v1_checks(tmp_path):
    path = tmp_path / "a.png"
    solid((255, 0, 0)).save(path)
    ev = photo.verify_photo("t", str(path), {"category": "pothole"}, photo.PhotoIndex(str(tmp_path / "i.json")),
                            use_clip=True, embedder=BrokenEmbedder())
    assert ev.details["clip_error"] == "RuntimeError" and ev.verdict == "inconclusive"
