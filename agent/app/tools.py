"""The six agent tools. Stub implementations (AGENT_USE_STUBS=1) are deterministic per ticket id so the
loop, trace and tests work before the Engine, Telegram and CLIP are wired. Every stub result is labelled."""
import hashlib

import httpx

from . import config, telegram
from .models import Evidence, Score
from .photo import PhotoIndex, verify_photo


def _h(ticket_id: str, salt: str = "") -> int:
    return int(hashlib.sha256((salt + ticket_id).encode()).hexdigest()[:8], 16)


def stub_truth_false(ticket_id: str) -> bool:
    """Hidden 'ground truth' for stubs: is this closure actually false?"""
    return _h(ticket_id) % 2 == 0


def _engine(method: str, path: str, **kw):
    r = httpx.request(method, config.ENGINE_URL + path, timeout=5, **kw)
    r.raise_for_status()
    return r.json()


def get_score(ticket_id: str) -> tuple[Score, str]:
    """Returns (score, source) where source is 'engine' or 'stub'."""
    if not config.USE_STUBS:
        try:
            return Score(**_engine("GET", f"/tickets/{ticket_id}/score")), "engine"
        except Exception:
            pass
    prior = 0.45 + (_h(ticket_id, "prior") % 30) / 100          # 0.45 .. 0.74: always uncertain
    return Score(ticket_id=ticket_id, p_false_closure=round(prior, 2), model_version="stub",
                 reasons=[{"feature": "stub", "value": 0, "shap": 0.0}],
                 eligible_checks=["photo", "satellite", "citizen", "human"],
                 satellite_eligible=_h(ticket_id, "sat") % 3 != 0), "stub"


def _get_ticket(ticket_id: str) -> dict | None:
    try:
        return _engine("GET", f"/tickets/{ticket_id}")
    except Exception:
        return None


def check_photo(ticket_id: str, closure_photo_url: str | None = None) -> Evidence:
    if not config.USE_STUBS:
        ticket = _get_ticket(ticket_id)
        url = closure_photo_url or (ticket or {}).get("closure_photo_url")
        if url:
            try:
                return verify_photo(ticket_id, url, ticket, PhotoIndex(), cost=config.TOOL_COSTS["check_photo"])
            except Exception as exc:   # missing file, bad URL, corrupt image: report it, do not kill the run
                return Evidence(ticket_id=ticket_id, check="photo", verdict="inconclusive", likelihood_ratio=1.0,
                                confidence=0.0, cost=config.TOOL_COSTS["check_photo"],
                                details={"reason": f"closure photo unreadable ({type(exc).__name__})"})
        return Evidence(ticket_id=ticket_id, check="photo", verdict="inconclusive", likelihood_ratio=1.0,
                        confidence=0.0, cost=config.TOOL_COSTS["check_photo"], details={"reason": "no closure photo"})
    bad = stub_truth_false(ticket_id)
    return Evidence(ticket_id=ticket_id, check="photo",
                    verdict="contradicts_fix" if bad else "supports_fix",
                    likelihood_ratio=5.0 if bad else 0.4, confidence=0.7,
                    cost=config.TOOL_COSTS["check_photo"], details={"stub": True})


def check_satellite(ticket_id: str, eligible: bool) -> Evidence:
    if not eligible:
        return Evidence(ticket_id=ticket_id, check="satellite", verdict="inconclusive", likelihood_ratio=1.0,
                        confidence=0.0, cost=0, details={"reason": "category not satellite-eligible"})
    if not config.USE_STUBS:
        try:
            return Evidence(**_engine("POST", "/satellite/check", json={"ticket_id": ticket_id}))
        except Exception:
            return Evidence(ticket_id=ticket_id, check="satellite", verdict="inconclusive", likelihood_ratio=1.0,
                            confidence=0.0, cost=0, details={"reason": "engine unreachable"})
    bad = stub_truth_false(ticket_id)
    return Evidence(ticket_id=ticket_id, check="satellite",
                    verdict="contradicts_fix" if bad else "supports_fix",
                    likelihood_ratio=4.0 if bad else 0.35, confidence=0.6,
                    cost=config.TOOL_COSTS["check_satellite"], details={"stub": True})


def ask_citizen(ticket_id: str) -> Evidence:
    """Real channel (Telegram) is asynchronous: send the message now, the reply becomes Evidence via the
    webhook. Stubs answer immediately so the loop works without a bot."""
    if not config.USE_STUBS:
        t = _get_ticket(ticket_id) or {}
        sent = False
        if telegram.has_contact(ticket_id):
            try:
                sent = telegram.send_request(ticket_id, t.get("category", "issue"), t.get("ward", "your area"),
                                             (t.get("closed_at") or "")[:10] or "recently")
            except Exception:
                sent = False
        return Evidence(ticket_id=ticket_id, check="citizen", verdict="inconclusive", likelihood_ratio=1.0,
                        confidence=0.0, cost=config.TOOL_COSTS["ask_citizen"] if sent else 0,
                        details={"channel": "telegram", "pending": sent,
                                 "reason": "awaiting reply" if sent else "no usable contact"})
    bad = stub_truth_false(ticket_id)
    return Evidence(ticket_id=ticket_id, check="citizen",
                    verdict="contradicts_fix" if bad else "supports_fix",
                    likelihood_ratio=6.0 if bad else 0.3, confidence=0.75,
                    cost=config.TOOL_COSTS["ask_citizen"], details={"stub": True, "channel": "stub"})


def request_human_spot_check(ticket_id: str) -> Evidence:
    bad = stub_truth_false(ticket_id)
    return Evidence(ticket_id=ticket_id, check="human",
                    verdict="contradicts_fix" if bad else "supports_fix",
                    likelihood_ratio=20.0 if bad else 0.05, confidence=0.95,
                    cost=config.TOOL_COSTS["request_human_spot_check"], details={"stub": True})
