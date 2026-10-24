"""Repeat offenders and duplicate requests. Small, honest statistics on data the Engine already holds.

Hotspots: a ward (or a closing officer, by hash) whose closed tickets are reopened clearly more often than the rest of
the same city. "Clearly" means a one-sided binomial test that survives a Bonferroni correction for the number of groups
tested, AND at least 1.5 times the city rate. It shows where reopens cluster; it does not say who is at fault, and a
reopen is only a proxy for a bad closure.
"""
import re
from typing import Any

from scipy.stats import binomtest

MIN_CLOSED = 30
MIN_RATIO = 1.5
ALPHA = 0.05

_STOP = {"a", "an", "the", "is", "are", "was", "in", "on", "at", "of", "to", "and", "near", "there", "this", "that", "it",
         "with", "for", "from", "by", "has", "have", "very", "big", "please", "my", "our"}


def hotspots(rows: list[dict[str, Any]], min_closed: int = MIN_CLOSED) -> list[dict[str, Any]]:
    """rows: {city, kind ('ward'|'closer'), key, done, reopened} for every group with at least one closed ticket."""
    by_city: dict[str, list[dict]] = {}
    for r in rows:
        by_city.setdefault(r["city"], []).append(r)
    out = []
    for city, group in by_city.items():
        wards = [g for g in group if g["kind"] == "ward"]
        total_done, total_reopen = sum(g["done"] for g in wards), sum(g["reopened"] for g in wards)
        if not total_done or not total_reopen:
            continue                      # this city has no reopen data, so nothing can be compared
        base = total_reopen / total_done
        for kind in ("ward", "closer"):
            tested = [g for g in group if g["kind"] == kind and g["done"] >= min_closed]
            for g in tested:
                rate = g["reopened"] / g["done"]
                p = binomtest(g["reopened"], g["done"], base, alternative="greater").pvalue
                if p * len(tested) < ALPHA and rate >= MIN_RATIO * base:     # Bonferroni across the groups tested
                    out.append({"city": city, "kind": kind, "key": g["key"], "closed": g["done"], "reopened": g["reopened"],
                                "rate": round(rate, 4), "city_rate": round(base, 4), "ratio": round(rate / base, 2),
                                "p_value": float(f"{p:.3g}")})
    return sorted(out, key=lambda r: (-r["ratio"], r["p_value"]))


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP and len(t) > 1}


def text_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def similar(candidates: list[dict[str, Any]], *, category: str, ward: str, text: str, limit: int = 3,
            min_similarity: float = 0.25) -> list[dict[str, Any]]:
    """Open website requests of the same category in the same ward whose wording overlaps. Needs a named ward: with no
    place there is nothing to say two requests are the same problem."""
    ward_key = ward.strip().casefold()
    if not ward_key or ward_key == "unspecified":
        return []
    out = []
    for c in candidates:
        if c["category"] != category or c["ward"].strip().casefold() != ward_key:
            continue
        s = text_similarity(text, c["text"])
        if s >= min_similarity:
            out.append({"ticket_id": c["ticket_id"], "text": c["text"][:200], "ward": c["ward"], "status": c["status"],
                        "created_at": c["created_at"], "similarity": round(s, 2)})
    return sorted(out, key=lambda r: -r["similarity"])[:limit]
