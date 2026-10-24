"""Module 3 (part): turn a citizen's reply into Evidence. Keyword/number map first (Q12 option D);
the LLM zero-shot fallback plugs in through the `fallback` argument once llm.py exists.

LRs: clear "No" ~ 6, "Partly" ~ 2, "Yes" ~ 0.3, no reply after 48 h ~ 1.2 (silence is weak evidence,
never a sign of satisfaction). Unparseable text is inconclusive, LR 1.0.
"""
import re
import unicodedata
from typing import Callable

from . import config
from .models import Evidence

LR_NO, LR_PARTLY, LR_YES, LR_SILENCE = 6.0, 2.0, 0.3, 1.2

# Intent -> keywords (lowercased; Devanagari and Kannada kept as-is). Whole-word match after normalisation.
KEYWORDS = {
    "yes": {"1", "yes", "y", "yeah", "yep", "fixed", "done", "ok", "okay", "haan", "han", "ha", "ho", "hoy",
            "theek", "thik", "हाँ", "हां", "हो", "होय", "ठीक", "हुआ", "झाले", "झालं", "ಹೌದು", "ಆಗಿದೆ"},
    "no": {"2", "no", "n", "nope", "not", "nahi", "nahin", "nai", "nako", "naahi", "nahi", "नहीं", "नही", "नाही",
           "नको", "नहि", "ಇಲ್ಲ", "ಆಗಿಲ್ಲ", "ಬೇಡ"},
    "partly": {"3", "partly", "partial", "partially", "half", "thoda", "thodasa", "kuch", "aanshik", "अंशतः",
               "थोड़ा", "थोडा", "काही", "ಸ್ವಲ್ಪ"},
    "stop": {"stop", "unsubscribe", "रुको", "बंद", "थांबा", "ನಿಲ್ಲಿಸಿ"},
}
NEGATORS = {"not", "never", "nahi", "nahin", "no", "नहीं", "नही", "नाही", "ಇಲ್ಲ"}

INTENT_EVIDENCE = {
    "no": ("contradicts_fix", LR_NO, 0.8),
    "partly": ("contradicts_fix", LR_PARTLY, 0.6),
    "yes": ("supports_fix", LR_YES, 0.7),
}

PROMPTS = {
    "en": "Your complaint about {category} near {area} was marked fixed on {date}. Was it fixed? "
          "Reply 1 Yes, 2 No, 3 Partly, or send a photo. Reply STOP to opt out.",
    "hi": "{area} के पास {category} की आपकी शिकायत {date} को हल बताई गई। क्या यह ठीक हुआ? "
          "1 हाँ, 2 नहीं, 3 थोड़ा, या फोटो भेजें। बंद करने के लिए STOP लिखें।",
    "mr": "{area} जवळील {category} बद्दलची तुमची तक्रार {date} रोजी सोडवली म्हणून नोंदवली. काम झाले का? "
          "1 होय, 2 नाही, 3 अंशतः, किंवा फोटो पाठवा. थांबण्यासाठी STOP लिहा.",
    "kn": "{area} ಬಳಿಯ {category} ಬಗ್ಗೆ ನಿಮ್ಮ ದೂರು {date} ರಂದು ಪರಿಹರಿಸಲಾಗಿದೆ ಎಂದು ಗುರುತಿಸಲಾಗಿದೆ. ಸರಿಪಡಿಸಲಾಗಿದೆಯೇ? "
          "1 ಹೌದು, 2 ಇಲ್ಲ, 3 ಸ್ವಲ್ಪ, ಅಥವಾ ಫೋಟೋ ಕಳುಹಿಸಿ. ನಿಲ್ಲಿಸಲು STOP ಬರೆಯಿರಿ.",
}


def build_prompt(lang: str, category: str, area: str, date: str) -> str:
    return PROMPTS.get(lang, PROMPTS["en"]).format(category=category, area=area, date=date)


def _tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text).lower()
    return re.findall(r"[\wऀ-ॿಀ-೿]+", text)


def parse_intent(text: str) -> str | None:
    """Return 'yes' | 'no' | 'partly' | 'stop' | None (None = needs the LLM fallback)."""
    toks = _tokens(text)
    if not toks:
        return None
    if len(toks) == 1 and toks[0] in ("1", "2", "3"):
        return {"1": "yes", "2": "no", "3": "partly"}[toks[0]]
    hits = {intent: [t for t in toks if t in words] for intent, words in KEYWORDS.items()}
    if hits["stop"]:
        return "stop"
    if hits["partly"]:
        return "partly"
    # "not fixed", "fixed nahi": a negator anywhere beats a positive word
    if any(t in NEGATORS for t in toks):
        return "no"
    if hits["no"]:
        return "no"
    if hits["yes"]:
        return "yes"
    return None


def reply_to_evidence(ticket_id: str, text: str, fallback: Callable[[str], str | None] | None = None,
                      has_photo: bool = False) -> Evidence:
    intent = parse_intent(text)
    source = "keyword"
    if intent is None and fallback is not None:
        intent, source = fallback(text), "llm"
    cost = config.TOOL_COSTS["ask_citizen"]
    if intent in INTENT_EVIDENCE:
        verdict, lr, conf = INTENT_EVIDENCE[intent]
        return Evidence(ticket_id=ticket_id, check="citizen", verdict=verdict, likelihood_ratio=lr,
                        confidence=conf, cost=cost,
                        details={"intent": intent, "parsed_by": source, "has_photo": has_photo})
    return Evidence(ticket_id=ticket_id, check="citizen", verdict="inconclusive", likelihood_ratio=1.0,
                    confidence=0.0, cost=cost,
                    details={"intent": intent or "unparsed", "parsed_by": source, "has_photo": has_photo})


def silence_evidence(ticket_id: str) -> Evidence:
    """No reply after 48 h. Weak evidence against the closure, never a sign of satisfaction."""
    return Evidence(ticket_id=ticket_id, check="citizen", verdict="inconclusive", likelihood_ratio=LR_SILENCE,
                    confidence=0.2, cost=config.TOOL_COSTS["ask_citizen"],
                    details={"intent": "no_reply", "after_hours": 48})
