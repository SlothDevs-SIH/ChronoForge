"""Which language a citizen is writing in, so the bot can answer in it. Script decides Kannada and the Devanagari pair;
Hindi and Marathi share a script, so a few very common function words split them. Latin script stays English (a
romanised Hindi reply such as "nahi" is understood by the reply parser regardless, and English replies are always safe)."""
import re

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_KANNADA = re.compile(r"[ಀ-೿]")
_MARATHI = {"आहे", "नाही", "झाले", "झालं", "काय", "तुम्ही", "आणि", "नको", "होय", "अजून", "अजूनही", "करा", "सोडवली"}
_HINDI = {"है", "नहीं", "हैं", "क्या", "आप", "और", "था", "हुआ", "नही", "हाँ", "हां", "की", "ठीक"}


def detect(text: str) -> str | None:
    """'en' | 'hi' | 'mr' | 'kn', or None when the text has no letters to judge (digits, emoji, button numbers)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return None
    if _KANNADA.search(text):
        return "kn"
    if _DEVANAGARI.search(text):
        words = set(re.findall(r"[ऀ-ॿ]+", text))
        mr, hi = len(words & _MARATHI), len(words & _HINDI)
        return "mr" if mr > hi else "hi"
    return "en" if len(text.split()) >= 3 else None   # one romanised word ("nahi", "haan") says nothing about language
