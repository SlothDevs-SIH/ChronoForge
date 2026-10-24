"""The six agent tools. Stub implementations (AGENT_USE_STUBS=1) are deterministic per ticket id so the
loop, trace and tests work before the Engine, Telegram and CLIP are wired. Every stub result is labelled."""
import hashlib

import httpx

from . import config, telegram
from .models import Evidence, Score
from .photo import PhotoIndex, verify_photo

_STUB = config.VC["stub_lr"]   # stub-only numbers (AGENT_USE_STUBS=1), kept with the other configured values


def _h(ticket_id: str, salt: str = "") -> int:
    return int(hashlib.sha256((salt + ticket_id).encode()).hexdigest()[:8], 16)


def stub_truth_false(ticket_id: str) -> bool:
    """Hidden 'ground truth' for stubs: is this closure actually false?"""
    return _h(ticket_id) % 2 == 0


class EngineUnavailable(RuntimeError):
    pass


def _engine(method: str, path: str, timeout: float = 5, **kw):
    if config.ENGINE_SERVICE_TOKEN:   # the Engine only talks to the Agent through this shared secret
        kw["headers"] = {**kw.get("headers", {}), "X-Service-Token": config.ENGINE_SERVICE_TOKEN}
    r = httpx.request(method, config.ENGINE_URL + path, timeout=timeout, **kw)
    r.raise_for_status()
    return r.json()


def get_score(ticket_id: str) -> tuple[Score, str]:
    """Returns (score, source) where source is 'engine' or 'stub'."""
    if not config.USE_STUBS:
        try:
            return Score(**_engine("GET", f"/tickets/{ticket_id}/score")), "engine"
        except Exception as exc:
            if not config.ALLOW_STUB_FALLBACK:   # real services are on: do not invent a prior for an unreachable Engine or unknown ticket
                raise EngineUnavailable(f"cannot get a score for {ticket_id} from the Engine ({type(exc).__name__})") from exc
    prior = 0.45 + (_h(ticket_id, "prior") % 30) / 100          # 0.45 .. 0.74: always uncertain
    return Score(ticket_id=ticket_id, p_false_closure=round(prior, 2), model_version="stub",
                 reasons=[{"feature": "stub", "value": 0, "shap": 0.0}],
                 eligible_checks=["photo", "satellite", "citizen", "human"],
                 satellite_eligible=_h(ticket_id, "sat") % 3 != 0), "stub"


def _get_ticket(ticket_id: str) -> dict | None:
    try:
        t = _engine("GET", f"/tickets/{ticket_id}")
    except Exception:
        return None
    return t


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
                    likelihood_ratio=_STUB["photo"]["bad"] if bad else _STUB["photo"]["good"], confidence=0.7,
                    cost=config.TOOL_COSTS["check_photo"], details={"stub": True})


def check_satellite(ticket_id: str, eligible: bool) -> Evidence:
    if not eligible:
        return Evidence(ticket_id=ticket_id, check="satellite", verdict="inconclusive", likelihood_ratio=1.0,
                        confidence=0.0, cost=0, details={"reason": "category not satellite-eligible"})
    if not config.USE_STUBS:
        try:
            # cached answer first (instant); only if the Engine has none, ask for a live read (20 to 60 s)
            ev = _engine("POST", "/satellite/check", json={"ticket_id": ticket_id, "cached_only": True}, timeout=10)
            if ev.get("details", {}).get("source") == "not_cached":
                ev = _engine("POST", "/satellite/check", json={"ticket_id": ticket_id}, timeout=config.SATELLITE_TIMEOUT)
            return Evidence(**ev)
        except Exception as exc:
            return Evidence(ticket_id=ticket_id, check="satellite", verdict="inconclusive", likelihood_ratio=1.0,
                            confidence=0.0, cost=0, details={"reason": f"satellite check failed ({type(exc).__name__})"})
    bad = stub_truth_false(ticket_id)
    return Evidence(ticket_id=ticket_id, check="satellite",
                    verdict="contradicts_fix" if bad else "supports_fix",
                    likelihood_ratio=_STUB["satellite"]["bad"] if bad else _STUB["satellite"]["good"], confidence=0.6,
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
                    likelihood_ratio=_STUB["citizen"]["bad"] if bad else _STUB["citizen"]["good"], confidence=0.75,
                    cost=config.TOOL_COSTS["ask_citizen"], details={"stub": True, "channel": "stub"})


def request_human_spot_check(ticket_id: str) -> Evidence:
    bad = stub_truth_false(ticket_id)
    return Evidence(ticket_id=ticket_id, check="human",
                    verdict="contradicts_fix" if bad else "supports_fix",
                    likelihood_ratio=_STUB["human"]["bad"] if bad else _STUB["human"]["good"], confidence=0.95,
                    cost=config.TOOL_COSTS["request_human_spot_check"], details={"stub": True})
