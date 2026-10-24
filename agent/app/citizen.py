"""Module 3 (part): turn a citizen's reply into Evidence, and the wording of every message the bot sends.
Keyword/number map first (Q12 option D); the LLM zero-shot fallback plugs in through the `fallback` argument.

LRs: clear "No" ~ 6, "Partly" ~ 2, "Yes" ~ 0.3, no reply after 48 h ~ 1.2 (silence is weak evidence,
never a sign of satisfaction). Unparseable text is inconclusive, LR 1.0.

Messages are plain text with blank lines and emoji so they read the same on Telegram and WhatsApp.
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
    "no": {"2", "no", "n", "nope", "not", "nahi", "nahin", "nai", "nako", "naahi", "नहीं", "नही", "नाही",
           "नको", "नहि", "ಇಲ್ಲ", "ಆಗಿಲ್ಲ", "ಬೇಡ",
           "still", "broken", "worse", "same", "pending", "nothing", "untouched", "unfixed", "unresolved",
           "abhi", "waisa", "vaisa", "tasach", "तसाच", "अभी", "वैसा", "वैसे", "अजूनही", "ಇನ್ನೂ"},
    "partly": {"3", "partly", "partial", "partially", "half", "thoda", "thodasa", "kuch", "aanshik", "अंशतः",
               "थोड़ा", "थोडा", "काही", "ಸ್ವಲ್ಪ"},
    "stop": {"stop", "unsubscribe", "रुको", "बंद", "थांबा", "ನಿಲ್ಲಿಸಿ"},
}
# "no problem" / "no issues" are good news, not a "no"
_GOOD_NEWS = re.compile(r"\b(no|zero)\s+(problems?|issues?|complaints?|worries)\b|\ball\s+(good|ok|okay|fine)\b")
_PARTIAL = re.compile(r"\bnot\s+(fully|completely|entirely|totally|wholly)\b|\bhalf\b")
NEGATORS = {"not", "never", "nahi", "nahin", "no", "नहीं", "नही", "नाही", "ಇಲ್ಲ"}

INTENT_EVIDENCE = {
    "no": ("contradicts_fix", LR_NO, 0.8),
    "partly": ("contradicts_fix", LR_PARTLY, 0.6),
    "yes": ("supports_fix", LR_YES, 0.7),
}

# ---- what the bot says -----------------------------------------------------------------------------------------
PROMPTS = {
    "en": ("🔔 Was your complaint fixed?\n\n"
           "Your complaint about {category} near {area} was marked as fixed on {date}.\n\n"
           "Please tap a button below, or reply with:\n"
           "1️⃣  Yes, it is fixed\n2️⃣  No, it is not fixed\n3️⃣  Partly fixed\n\n"
           "📷 You can also send a photo.\nReply STOP to opt out."),
    "hi": ("🔔 क्या आपकी शिकायत हल हुई?\n\n"
           "{area} के पास {category} की आपकी शिकायत {date} को हल बताई गई।\n\n"
           "कृपया नीचे बटन दबाएँ, या जवाब दें:\n"
           "1️⃣  हाँ, ठीक हो गया\n2️⃣  नहीं, ठीक नहीं हुआ\n3️⃣  थोड़ा ठीक हुआ\n\n"
           "📷 आप फोटो भी भेज सकते हैं।\nबंद करने के लिए STOP लिखें।"),
    "mr": ("🔔 तुमची तक्रार सोडवली का?\n\n"
           "{area} जवळील {category} बद्दलची तुमची तक्रार {date} रोजी सोडवली म्हणून नोंदवली.\n\n"
           "कृपया खालील बटण दाबा, किंवा उत्तर द्या:\n"
           "1️⃣  होय, काम झाले\n2️⃣  नाही, काम झाले नाही\n3️⃣  अंशतः झाले\n\n"
           "📷 तुम्ही फोटोही पाठवू शकता.\nथांबण्यासाठी STOP लिहा."),
    "kn": ("🔔 ನಿಮ್ಮ ದೂರು ಪರಿಹಾರವಾಯಿತೇ?\n\n"
           "{area} ಬಳಿಯ {category} ಬಗ್ಗೆ ನಿಮ್ಮ ದೂರು {date} ರಂದು ಪರಿಹರಿಸಲಾಗಿದೆ ಎಂದು ಗುರುತಿಸಲಾಗಿದೆ.\n\n"
           "ದಯವಿಟ್ಟು ಕೆಳಗಿನ ಬಟನ್ ಒತ್ತಿ, ಅಥವಾ ಉತ್ತರಿಸಿ:\n"
           "1️⃣  ಹೌದು, ಸರಿಯಾಗಿದೆ\n2️⃣  ಇಲ್ಲ, ಸರಿಯಾಗಿಲ್ಲ\n3️⃣  ಸ್ವಲ್ಪ ಸರಿಯಾಗಿದೆ\n\n"
           "📷 ನೀವು ಫೋಟೋ ಕೂಡ ಕಳುಹಿಸಬಹುದು.\nನಿಲ್ಲಿಸಲು STOP ಬರೆಯಿರಿ."),
}
BUTTONS = {  # (yes, no, partly)
    "en": ("✅ Yes", "❌ No", "🟡 Partly"),
    "hi": ("✅ हाँ", "❌ नहीं", "🟡 थोड़ा"),
    "mr": ("✅ होय", "❌ नाही", "🟡 अंशतः"),
    "kn": ("✅ ಹೌದು", "❌ ಇಲ್ಲ", "🟡 ಸ್ವಲ್ಪ"),
}
ACK = {
    "en": {
        "stale": "ℹ️ That question was already answered or is no longer open.\n\nThank you!",
        "yes": "✅ Thank you!\n\nWe have recorded that the problem is fixed. Glad it was sorted out.",
        "no": "🙏 Thank you for telling us.\n\nWe have recorded that the problem is NOT fixed. "
              "The municipal team will review this closure.",
        "partly": "🙏 Thank you.\n\nWe have recorded that the problem is only partly fixed. "
                  "The municipal team will review it.",
        "photo": "📷 Thanks, we received your photo and will add it to the review.",
        "unclear": "🤔 Sorry, I did not understand that.\n\nPlease tap a button below, or reply with:\n"
                   "1️⃣  Yes\n2️⃣  No\n3️⃣  Partly",
        "stop": "👋 You have been unsubscribed.\n\nWe will not message you about this complaint again.",
        "idle": "👋 Hello!\n\nThere is no open question for you right now. "
                "If your complaint needs a check, I will message you here.",
        "help": "ℹ️ How this works\n\nWhen a complaint you filed is marked fixed, I will ask you whether it really was.\n\n"
                "Reply with a button or with 1, 2 or 3. Reply STOP to opt out.",
    },
    "hi": {
        "stale": "ℹ️ इस प्रश्न का उत्तर पहले ही दिया जा चुका है या यह अब खुला नहीं है।\n\nधन्यवाद!",
        "yes": "✅ धन्यवाद!\n\nहमने दर्ज किया कि समस्या ठीक हो गई है।",
        "no": "🙏 बताने के लिए धन्यवाद।\n\nहमने दर्ज किया कि समस्या ठीक नहीं हुई है। नगर निगम की टीम इसकी समीक्षा करेगी।",
        "partly": "🙏 धन्यवाद।\n\nहमने दर्ज किया कि समस्या आंशिक रूप से ही ठीक हुई है। टीम इसकी समीक्षा करेगी।",
        "photo": "📷 धन्यवाद, आपकी फोटो मिल गई। इसे समीक्षा में जोड़ा जाएगा।",
        "unclear": "🤔 माफ़ कीजिए, मैं समझ नहीं पाया।\n\nकृपया बटन दबाएँ, या जवाब दें:\n1️⃣  हाँ\n2️⃣  नहीं\n3️⃣  थोड़ा",
        "stop": "👋 आपको सूची से हटा दिया गया है।\n\nइस शिकायत के बारे में हम दोबारा संदेश नहीं भेजेंगे।",
        "idle": "👋 नमस्ते!\n\nअभी आपके लिए कोई खुला प्रश्न नहीं है।",
        "help": "ℹ️ यह कैसे काम करता है\n\nजब आपकी शिकायत हल बताई जाती है, तो मैं पूछता हूँ कि क्या सच में हल हुई।\n\n"
                "बटन दबाएँ या 1, 2, 3 लिखें। बंद करने के लिए STOP लिखें।",
    },
    "mr": {
        "stale": "ℹ️ या प्रश्नाचे उत्तर आधीच दिले आहे किंवा तो आता खुला नाही.\n\nधन्यवाद!",
        "yes": "✅ धन्यवाद!\n\nसमस्या सुटल्याची नोंद केली आहे.",
        "no": "🙏 कळवल्याबद्दल धन्यवाद.\n\nसमस्या सुटलेली नाही अशी नोंद केली आहे. महानगरपालिकेची टीम याचा आढावा घेईल.",
        "partly": "🙏 धन्यवाद.\n\nसमस्या अंशतःच सुटल्याची नोंद केली आहे. टीम आढावा घेईल.",
        "photo": "📷 धन्यवाद, तुमचा फोटो मिळाला. तो आढाव्यात जोडला जाईल.",
        "unclear": "🤔 माफ करा, मला समजले नाही.\n\nकृपया बटण दाबा, किंवा उत्तर द्या:\n1️⃣  होय\n2️⃣  नाही\n3️⃣  अंशतः",
        "stop": "👋 तुम्हाला यादीतून काढले आहे.\n\nया तक्रारीबद्दल आम्ही पुन्हा संदेश पाठवणार नाही.",
        "idle": "👋 नमस्कार!\n\nसध्या तुमच्यासाठी कोणताही प्रश्न नाही.",
        "help": "ℹ️ हे कसे चालते\n\nतुमची तक्रार सोडवली गेली की मी विचारतो खरंच सुटली का.\n\n"
                "बटण दाबा किंवा 1, 2, 3 लिहा. थांबण्यासाठी STOP लिहा.",
    },
    "kn": {
        "stale": "ℹ️ ಈ ಪ್ರಶ್ನೆಗೆ ಈಗಾಗಲೇ ಉತ್ತರಿಸಲಾಗಿದೆ ಅಥವಾ ಅದು ಈಗ ತೆರೆದಿಲ್ಲ.\n\nಧನ್ಯವಾದಗಳು!",
        "yes": "✅ ಧನ್ಯವಾದಗಳು!\n\nಸಮಸ್ಯೆ ಪರಿಹಾರವಾಗಿದೆ ಎಂದು ದಾಖಲಿಸಲಾಗಿದೆ.",
        "no": "🙏 ತಿಳಿಸಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು.\n\nಸಮಸ್ಯೆ ಪರಿಹಾರವಾಗಿಲ್ಲ ಎಂದು ದಾಖಲಿಸಲಾಗಿದೆ. ಪಾಲಿಕೆ ತಂಡ ಇದನ್ನು ಪರಿಶೀಲಿಸುತ್ತದೆ.",
        "partly": "🙏 ಧನ್ಯವಾದಗಳು.\n\nಸಮಸ್ಯೆ ಭಾಗಶಃ ಮಾತ್ರ ಪರಿಹಾರವಾಗಿದೆ ಎಂದು ದಾಖಲಿಸಲಾಗಿದೆ.",
        "photo": "📷 ಧನ್ಯವಾದಗಳು, ನಿಮ್ಮ ಫೋಟೋ ಸಿಕ್ಕಿದೆ.",
        "unclear": "🤔 ಕ್ಷಮಿಸಿ, ನನಗೆ ಅರ್ಥವಾಗಲಿಲ್ಲ.\n\nದಯವಿಟ್ಟು ಬಟನ್ ಒತ್ತಿ, ಅಥವಾ ಉತ್ತರಿಸಿ:\n1️⃣  ಹೌದು\n2️⃣  ಇಲ್ಲ\n3️⃣  ಸ್ವಲ್ಪ",
        "stop": "👋 ನಿಮ್ಮನ್ನು ಪಟ್ಟಿಯಿಂದ ತೆಗೆದುಹಾಕಲಾಗಿದೆ.",
        "idle": "👋 ನಮಸ್ಕಾರ!\n\nಈಗ ನಿಮಗಾಗಿ ಯಾವುದೇ ಪ್ರಶ್ನೆ ಇಲ್ಲ.",
        "help": "ℹ️ ಇದು ಹೇಗೆ ಕೆಲಸ ಮಾಡುತ್ತದೆ\n\nಬಟನ್ ಒತ್ತಿ ಅಥವಾ 1, 2, 3 ಬರೆಯಿರಿ. ನಿಲ್ಲಿಸಲು STOP ಬರೆಯಿರಿ.",
    },
}


def _lang(lang: str) -> str:
    return lang if lang in PROMPTS else "en"


def build_prompt(lang: str, category: str, area: str, date: str) -> str:
    return PROMPTS[_lang(lang)].format(category=category, area=area, date=date)


def button_labels(lang: str) -> tuple[str, str, str]:
    return BUTTONS[_lang(lang)]


def ack_text(lang: str, kind: str) -> str:
    """kind: yes | no | partly | photo | unclear | stop | idle | help"""
    return ACK[_lang(lang)].get(kind) or ACK["en"][kind]


# ---- understanding replies -------------------------------------------------------------------------------------
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
    low = " ".join(toks)
    if hits["partly"] or _PARTIAL.search(low):
        return "partly"
    if _GOOD_NEWS.search(low):
        return "yes"
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
