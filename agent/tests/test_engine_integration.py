"""Engine integration behaviour added when the Agent and the Engine were joined (not part of Ayush's original suite).

- real mode (AGENT_USE_STUBS=0) must fail loudly when the Engine cannot give a score, never invent a stub prior
- the satellite tool asks for the cached answer first (instant) and only then for a live read, with a long timeout
"""
import httpx
import pytest

from app import agent, config, tools
from app.models import Evidence


def sat_payload(source="cached", verdict="contradicts_fix", lr=1.25):
    return {"evidence_id": "e1", "ticket_id": "T", "check": "satellite", "verdict": verdict, "likelihood_ratio": lr,
            "confidence": 0.2, "cost": 3, "details": {"source": source}, "created_at": "2026-10-24T00:00:00Z"}


@pytest.fixture
def real_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_STUBS", False)
    monkeypatch.setattr(config, "ALLOW_STUB_FALLBACK", False)


def test_real_mode_unreachable_engine_raises_instead_of_inventing_a_prior(real_mode):
    with pytest.raises(tools.EngineUnavailable):
        tools.get_score("T-1")


def test_a_run_for_an_unscorable_ticket_ends_in_error_with_a_clear_trace(real_mode):
    run_id = agent.start_run("NO-SUCH-TICKET")
    with pytest.raises(tools.EngineUnavailable):
        agent.execute(run_id, delay=0)
    run = agent.RUNS[run_id]
    assert run.status == "error" and run.verdict is None
    assert any("cannot get a score" in e.summary for e in run.events)


def test_stub_fallback_is_available_only_when_explicitly_allowed(real_mode, monkeypatch):
    monkeypatch.setattr(config, "ALLOW_STUB_FALLBACK", True)
    score, source = tools.get_score("T-1")
    assert source == "stub" and score.model_version == "stub"


def test_stub_mode_is_unchanged(monkeypatch):
    monkeypatch.setattr(config, "USE_STUBS", True)
    assert tools.get_score("T-1")[1] == "stub"


def test_satellite_uses_the_cached_answer_and_makes_one_call(real_mode, monkeypatch):
    calls = []
    monkeypatch.setattr(tools, "_engine", lambda method, path, timeout=5, **kw: calls.append((path, kw["json"], timeout)) or sat_payload("cached"))
    ev = tools.check_satellite("T", True)
    assert isinstance(ev, Evidence) and ev.likelihood_ratio == 1.25
    assert calls == [("/satellite/check", {"ticket_id": "T", "cached_only": True}, 10)]


def test_satellite_falls_back_to_a_live_read_with_a_long_timeout(real_mode, monkeypatch):
    calls = []

    def fake(method, path, timeout=5, **kw):
        calls.append((kw["json"], timeout))
        return sat_payload("not_cached", "inconclusive", 1.0) if kw["json"].get("cached_only") else sat_payload("live")
    monkeypatch.setattr(tools, "_engine", fake)
    ev = tools.check_satellite("T", True)
    assert ev.details["source"] == "live"
    assert calls[0] == ({"ticket_id": "T", "cached_only": True}, 10)
    assert calls[1] == ({"ticket_id": "T"}, config.SATELLITE_TIMEOUT) and config.SATELLITE_TIMEOUT >= 60   # a live read takes 20 to 60 s


def test_a_failed_satellite_call_abstains_at_no_cost_with_an_honest_reason(real_mode, monkeypatch):
    def boom(*a, **k):
        raise httpx.ReadTimeout("slow")
    monkeypatch.setattr(tools, "_engine", boom)
    ev = tools.check_satellite("T", True)
    assert ev.verdict == "inconclusive" and ev.cost == 0 and "satellite check failed" in ev.details["reason"]
    assert "unreachable" not in ev.details["reason"]


def test_ineligible_satellite_never_calls_the_engine(real_mode, monkeypatch):
    monkeypatch.setattr(tools, "_engine", lambda *a, **k: pytest.fail("must not call the Engine"))
    ev = tools.check_satellite("T", False)
    assert ev.verdict == "inconclusive" and ev.cost == 0


def test_engine_helper_passes_the_requested_timeout(monkeypatch):
    seen = {}

    class R:
        def raise_for_status(self): pass
        def json(self): return {}
    monkeypatch.setattr(httpx, "request", lambda method, url, timeout=None, **kw: seen.update(timeout=timeout) or R())
    tools._engine("GET", "/x", timeout=77)
    assert seen["timeout"] == 77
    tools._engine("GET", "/x")
    assert seen["timeout"] == 5
