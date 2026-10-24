import pytest
from pydantic import BaseModel

from app import config, llm, llm_planner, planner
from app.models import Evidence


class Out(BaseModel):
    x: int


@pytest.fixture(autouse=True)
def providers(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDERS", ["gemini", "openai"])
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k1")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "k2")


def inject(monkeypatch, **fns):
    monkeypatch.setattr(llm, "PROVIDERS", fns)


def down(prompt):
    raise ConnectionError


def test_first_provider_wins(monkeypatch):
    inject(monkeypatch, gemini=lambda p: '{"x": 1}', openai=lambda p: '{"x": 2}')
    assert llm.complete_json("q", Out) == (Out(x=1), "gemini")


def test_invalid_output_retries_once_then_next_provider(monkeypatch):
    calls = []

    def bad(prompt):
        calls.append(1)
        return "not json"
    inject(monkeypatch, gemini=bad, openai=lambda p: '{"x": 2}')
    assert llm.complete_json("q", Out) == (Out(x=2), "openai")
    assert len(calls) == 2


def test_network_error_skips_without_retry(monkeypatch):
    calls = []

    def flaky(prompt):
        calls.append(1)
        raise ConnectionError
    inject(monkeypatch, gemini=flaky, openai=lambda p: '{"x": 3}')
    assert llm.complete_json("q", Out)[1] == "openai" and len(calls) == 1


def test_all_fail_raises(monkeypatch):
    inject(monkeypatch, gemini=down, openai=down)
    with pytest.raises(llm.LLMError):
        llm.complete_json("q", Out)


def test_no_keys_means_no_providers(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    assert llm.available_providers() == []
    with pytest.raises(llm.LLMError):
        llm.complete_json("q", Out)


def state(**kw):
    return planner.PlanState(budget_left=kw.pop("budget_left", 10), satellite_eligible=kw.pop("sat", True), **kw)


def test_llm_choice_is_used_when_valid(monkeypatch):
    inject(monkeypatch, gemini=lambda p: '{"tool": "check_satellite", "reason": "photo is weak"}')
    tool, why = llm_planner.llm_planner(state())
    assert tool == "check_satellite" and why.startswith("[gemini]")


def test_guard_rejects_ineligible_llm_choice_and_falls_back(monkeypatch):
    inject(monkeypatch, gemini=lambda p: '{"tool": "check_satellite", "reason": "x"}')
    tool, why = llm_planner.llm_planner(state(sat=False))
    assert tool == "check_photo" and "guard rejected" in why


def test_unaffordable_llm_choice_falls_back(monkeypatch):
    inject(monkeypatch, gemini=lambda p: '{"tool": "request_human_spot_check", "reason": "x"}')
    tool, why = llm_planner.llm_planner(state(budget_left=5))
    assert tool != "request_human_spot_check" and "guard rejected" in why


def test_llm_down_falls_back_to_deterministic(monkeypatch):
    inject(monkeypatch, gemini=down, openai=down)
    tool, why = llm_planner.llm_planner(state())
    assert tool == "check_photo" and "fallback" in why


def test_stop_ends_investigation(monkeypatch):
    inject(monkeypatch, gemini=lambda p: '{"tool": "stop", "reason": "enough"}')
    assert llm_planner.llm_planner(state())[0] is None


def test_prompt_has_no_identifiers():
    ev = Evidence(ticket_id="SECRET-123", check="photo", verdict="supports_fix", likelihood_ratio=0.5,
                  confidence=0.5)
    p = llm_planner._prompt(state(prior=0.6, posterior=0.6, evidence=[ev]), ["check_photo"])
    assert "SECRET-123" not in p


def test_classify_reply(monkeypatch):
    inject(monkeypatch, gemini=lambda p: '{"intent": "no"}')
    assert llm_planner.classify_reply("kaam nahi hua yaar") == "no"
    inject(monkeypatch, gemini=lambda p: '{"intent": "unclear"}')
    assert llm_planner.classify_reply("???") is None
