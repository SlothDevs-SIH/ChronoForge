import pytest

from app import citizen


@pytest.mark.parametrize("text,intent", [
    ("1", "yes"), ("2", "no"), ("3", "partly"),
    ("Yes", "yes"), ("yes it is fixed", "yes"), ("not fixed", "no"), ("fixed nahi hua", "no"),
    ("haan ho gaya", "yes"), ("नहीं", "no"), ("नाही झाले", "no"), ("होय", "yes"), ("ಇಲ್ಲ", "no"),
    ("thoda hua", "partly"), ("partly done", "partly"), ("STOP", "stop"), ("", None), ("what is this?", None),
])
def test_parse_intent(text, intent):
    assert citizen.parse_intent(text) == intent


def test_no_reply_maps_to_contradicts_with_high_lr():
    ev = citizen.reply_to_evidence("t1", "2")
    assert ev.verdict == "contradicts_fix" and ev.likelihood_ratio == citizen.LR_NO and ev.check == "citizen"


def test_yes_supports_fix():
    ev = citizen.reply_to_evidence("t1", "yes")
    assert ev.verdict == "supports_fix" and ev.likelihood_ratio == citizen.LR_YES


def test_unparsed_uses_fallback_then_is_inconclusive():
    ev = citizen.reply_to_evidence("t1", "road looks weird", fallback=lambda t: "no")
    assert ev.details["parsed_by"] == "llm" and ev.verdict == "contradicts_fix"
    ev = citizen.reply_to_evidence("t1", "road looks weird")
    assert ev.verdict == "inconclusive" and ev.likelihood_ratio == 1.0


def test_silence_is_weak_and_never_supports():
    ev = citizen.silence_evidence("t1")
    assert ev.likelihood_ratio == citizen.LR_SILENCE and ev.verdict != "supports_fix"


def test_prompt_languages():
    for lang in ("en", "hi", "mr", "kn", "other"):
        assert "STOP" in citizen.build_prompt(lang, "pothole", "MG Road", "20 Oct")
