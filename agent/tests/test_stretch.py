import numpy as np
from PIL import Image

from app import agent, audit, config, dino_check, llm, photo, skeptic, telegram, tools
from tests.test_core import ticket_with


def inject(monkeypatch, **fns):
    monkeypatch.setattr(config, "LLM_PROVIDERS", ["gemini"])
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(llm, "PROVIDERS", fns)


def bad_ticket():
    return ticket_with(True)


def test_skeptic_downgrades_when_it_finds_a_hole(monkeypatch):
    monkeypatch.setattr(config, "USE_SKEPTIC", True)
    inject(monkeypatch, gemini=lambda p: '{"hole_found": true, "argument": "single weak source"}')
    run_id = agent.start_run(bad_ticket())
    v = agent.execute(run_id, delay=0)
    assert v.state == "cannot_tell" and v.recommended_action == "human_spot_check"
    assert any("skeptic" in e.summary and "Downgrading" in e.summary for e in agent.RUNS[run_id].events)
    assert audit.verify()["ok"]


def test_skeptic_that_finds_no_hole_leaves_verdict(monkeypatch):
    monkeypatch.setattr(config, "USE_SKEPTIC", True)
    inject(monkeypatch, gemini=lambda p: '{"hole_found": false, "argument": "consistent evidence"}')
    v = agent.execute(agent.start_run(bad_ticket()), delay=0)
    assert v.state == "likely_not_fixed"


def test_skeptic_unavailable_leaves_verdict_and_says_so(monkeypatch):
    monkeypatch.setattr(config, "USE_SKEPTIC", True)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    run_id = agent.start_run(bad_ticket())
    v = agent.execute(run_id, delay=0)
    assert v.state == "likely_not_fixed"
    assert any("skeptic unavailable" in e.summary for e in agent.RUNS[run_id].events)


def test_skeptic_off_by_default(monkeypatch):
    called = []
    monkeypatch.setattr(skeptic, "review", lambda *a: called.append(1))
    agent.execute(agent.start_run(bad_ticket()), delay=0)
    assert not called


class FakeDino:
    def image(self, img):
        v = np.array(img.convert("RGB").resize((1, 1)).getpixel((0, 0)), dtype=float)
        return v / (np.linalg.norm(v) or 1)


def solid(c):
    return Image.new("RGB", (8, 8), c)


def test_dino_flags_different_scene_and_passes_same():
    f, p, d = dino_check.dino_checks(solid((255, 0, 0)), solid((0, 255, 0)), FakeDino())
    assert f == ["same_scene"] and d["same_scene"]["dino_cosine"] < dino_check.DIFFERENT_SCENE
    f, p, _ = dino_check.dino_checks(solid((200, 10, 10)), solid((255, 0, 0)), FakeDino())
    assert p == ["same_scene"] and not f
    assert dino_check.dino_checks(solid((1, 1, 1)), None, FakeDino()) == ([], [], {})


def test_verify_photo_uses_dino_and_degrades(tmp_path):
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    solid((255, 0, 0)).save(a)
    solid((0, 255, 0)).save(b)
    idx = photo.PhotoIndex(str(tmp_path / "i.json"))
    ev = photo.verify_photo("t", str(a), {}, idx, use_clip=False, use_dino=True,
                            complaint_photo=str(b), dino_embedder=FakeDino())
    assert "same_scene" in ev.details["flags"] and ev.verdict == "contradicts_fix"

    class Boom:
        def image(self, i):
            raise RuntimeError
    ev = photo.verify_photo("t", str(a), {}, idx, use_clip=False, use_dino=True,
                            complaint_photo=str(b), dino_embedder=Boom())
    assert ev.details["dino_error"] == "RuntimeError"


def test_voice_note_is_transcribed_then_parsed(monkeypatch):
    telegram.register_contact("t1", 7)
    telegram.send_request("t1", "pothole", "x", "y", sender=lambda c, t: None)
    monkeypatch.setattr(telegram, "transcribe_voice", lambda file_id: "nahi hua")
    ev = telegram.handle_update({"message": {"chat": {"id": 7}, "voice": {"file_id": "f"}}})
    assert ev.verdict == "contradicts_fix"


def test_transcribe_voice_helper_and_failure():
    assert telegram.transcribe_voice("f", fetch=lambda: b"audio", transcriber=lambda b: "haan") == "haan"

    def boom(b):
        raise llm.LLMError("x")
    assert telegram.transcribe_voice("f", fetch=lambda: b"audio", transcriber=boom) == ""


def test_transcribe_needs_key(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    try:
        llm.transcribe(b"x")
        assert False
    except llm.LLMError:
        pass


def test_score_alone_never_gives_a_verdict(monkeypatch):
    """Contract: even a very high prior needs at least one independent check first."""
    from app.models import Score
    monkeypatch.setattr(tools, "get_score", lambda tid: (Score(
        ticket_id=tid, p_false_closure=0.95, eligible_checks=["photo"], satellite_eligible=False), "test"))
    run_id = agent.start_run("T-high-prior")
    agent.execute(run_id, delay=0)
    assert agent.RUNS[run_id].evidence


def test_unreadable_closure_photo_is_inconclusive_not_a_crash(monkeypatch):
    monkeypatch.setattr(config, "USE_STUBS", False)
    monkeypatch.setattr(tools, "_get_ticket", lambda tid: {"closure_photo_url": "demo/photos/missing.jpg"})
    ev = tools.check_photo("t")
    assert ev.verdict == "inconclusive" and ev.likelihood_ratio == 1.0 and "unreadable" in ev.details["reason"]


def test_no_conclusive_check_means_cannot_tell(monkeypatch):
    from app.models import Evidence, Score
    monkeypatch.setattr(tools, "get_score", lambda tid: (Score(
        ticket_id=tid, p_false_closure=0.9, eligible_checks=["photo"], satellite_eligible=False), "test"))
    monkeypatch.setattr(tools, "check_photo", lambda tid, url=None: Evidence(
        ticket_id=tid, check="photo", verdict="inconclusive", likelihood_ratio=1.0, confidence=0.0, cost=1))
    monkeypatch.setattr(tools, "ask_citizen", lambda tid: Evidence(
        ticket_id=tid, check="citizen", verdict="inconclusive", likelihood_ratio=1.0, confidence=0.0, cost=0))
    v = agent.execute(agent.start_run("T-inconclusive"), delay=0)
    assert v.state == "cannot_tell" and v.recommended_action == "human_spot_check"
