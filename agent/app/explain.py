"""Plain-language reasons behind a verdict, for the administrator who has to approve or reject it.

Built only from the evidence the agent actually recorded: nothing is guessed and nothing is added. Each line says what
a check found and which way it points. No timing or "closed too fast" claim is made, because that signal showed no
effect in our data."""
import json

from .db import get_conn
from .models import Evidence

PHOTO_FLAGS = {
    "duplicate": "The closure photo matches a photo already used on {nearest_ticket}.",
    "location": "The closure photo was taken {distance_m:.0f} m from the reported place.",
    "timestamp": "The closure photo was taken {days_before_closure:.0f} days before the ticket was closed.",
    "scene": "The closure photo still appears to show the problem.",
    "before_after": "The closure photo looks like a different place from the complaint photo.",
    "same_scene": "The closure photo looks like a different place from the complaint photo.",
}
CITIZEN = {
    "no": "The citizen said it is not fixed.",
    "partly": "The citizen said it is only partly fixed.",
    "yes": "The citizen said it is fixed.",
    "no_reply": "The citizen did not answer after two days (a weak signal, not proof).",
}


def _photo(ev: Evidence) -> tuple[str, list[str]]:
    d = ev.details or {}
    checks = d.get("checks", {})
    if ev.verdict == "contradicts_fix":
        lines = []
        for flag in d.get("flags", []):
            ctx = {"nearest_ticket": checks.get("duplicate", {}).get("nearest_ticket", "another ticket"),
                   "distance_m": checks.get("location", {}).get("distance_m", 0),
                   "days_before_closure": checks.get("timestamp", {}).get("days_before_closure", 0)}
            lines.append(PHOTO_FLAGS.get(flag, f"The closure photo failed the {flag} check.").format(**ctx))
        return "against", lines or ["The closure photo failed a check."]
    if ev.verdict == "supports_fix":
        return "for", ["The closure photo passed the checks that could be run (no duplicate; place and time consistent where known)."]
    return "none", ["The closure photo could not be checked (no photo or no usable data)."]


def line_for(ev: Evidence) -> tuple[str, list[str]]:
    """(direction, sentences). direction: 'against' the closure, 'for' it, or 'none' (could not tell)."""
    if ev.check == "citizen":
        intent = (ev.details or {}).get("intent", "")
        if intent in CITIZEN:
            return ("for" if intent == "yes" else "against" if ev.verdict == "contradicts_fix" or intent == "no_reply" else "none"), [CITIZEN[intent]]
        return "none", ["The citizen's reply could not be understood."]
    if ev.check == "photo":
        return _photo(ev)
    if ev.check == "satellite":
        if ev.verdict == "contradicts_fix":
            return "against", ["Satellite imagery shows no unusual change at the site between the two dates (weak evidence: small works are invisible at 10 m)."]
        if ev.verdict == "supports_fix":
            return "for", ["Satellite imagery shows an unusual change at the site, consistent with work being done."]
        return "none", ["The satellite check did not apply to this kind of problem or could not be run."]
    if ev.check == "human":
        return ("against" if ev.verdict == "contradicts_fix" else "for" if ev.verdict == "supports_fix" else "none"), ["A person inspected the site."]
    return "none", []


def for_verdict(snapshot: dict) -> dict:
    """{'summary', 'against', 'for', 'unknown'} for an approval's verdict snapshot."""
    ids = snapshot.get("evidence_ids") or []
    evidence: list[Evidence] = []
    if ids:
        marks = ",".join("?" * len(ids))
        for r in get_conn().execute(f"SELECT body FROM evidence WHERE evidence_id IN ({marks})", ids).fetchall():
            evidence.append(Evidence.model_validate(json.loads(r["body"])))
    out = {"against": [], "for": [], "unknown": []}
    for ev in evidence:
        direction, lines = line_for(ev)
        out[{"against": "against", "for": "for", "none": "unknown"}[direction]].extend(lines)
    prior, post = snapshot.get("prior"), snapshot.get("posterior")
    out["summary"] = (f"Chance this closure is false: {prior:.0%} at the start, {post:.0%} after the checks. "
                      "The starting figure comes from the pattern of past closures, not from this ticket's photos." if prior is not None and post is not None else "")
    if not evidence:
        out["unknown"].append("No independent check has been recorded for this case yet.")
    return out
