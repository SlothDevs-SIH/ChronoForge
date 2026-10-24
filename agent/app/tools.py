"""Tool layer. Real: engine calls. STUBS (flagged details.stub=true): photo, citizen, human.

AYUSH: replace stub_photo with imagehash + EXIF + CLIP; stub_citizen is replaced by the Telegram/WhatsApp
round trip (the reply arrives asynchronously, so the real tool sends and returns inconclusive until it lands).
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from . import config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Engine(Protocol):
    async def get_score(self, ticket_id: str) -> dict[str, Any]: ...
    async def satellite_check(self, ticket_id: str) -> dict[str, Any]: ...
    async def reopen(self, ticket_id: str) -> dict[str, Any]: ...
    async def escalate(self, ticket_id: str) -> dict[str, Any]: ...
    async def get_ticket(self, ticket_id: str) -> dict[str, Any]: ...


class HttpEngine:
    def __init__(self, base_url: str = config.ENGINE_URL) -> None:
        self._c = httpx.AsyncClient(base_url=base_url, timeout=90)

    async def _get(self, path: str) -> dict[str, Any]:
        r = await self._c.get(path)
        r.raise_for_status()
        return r.json()

    async def _post(self, path: str, body: dict | None = None) -> dict[str, Any]:
        r = await self._c.post(path, json=body)
        r.raise_for_status()
        return r.json()

    async def get_score(self, ticket_id: str) -> dict[str, Any]:
        return await self._get(f"/tickets/{ticket_id}/score")

    async def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        return await self._get(f"/tickets/{ticket_id}")

    async def satellite_check(self, ticket_id: str) -> dict[str, Any]:
        return await self._post("/satellite/check", {"ticket_id": ticket_id})

    async def reopen(self, ticket_id: str) -> dict[str, Any]:
        return await self._post(f"/muni/tickets/{ticket_id}/reopen")

    async def escalate(self, ticket_id: str) -> dict[str, Any]:
        return await self._post(f"/muni/tickets/{ticket_id}/escalate")


def _evidence(ticket_id: str, check: str, verdict: str, lr: float, conf: float, cost: int, details: dict) -> dict[str, Any]:
    return {
        "evidence_id": str(uuid.uuid4()), "ticket_id": ticket_id, "check": check, "verdict": verdict,
        "likelihood_ratio": lr, "confidence": conf, "cost": cost, "details": details, "created_at": _now(),
    }


def stub_photo(ticket_id: str, prior: float, model_version: str = "") -> dict[str, Any]:
    """STUB: plumbing only, not a real check. It must never produce a verdict on a real ticket, so it returns NO
    information unless the ticket is one of the six contract fixtures (model_version "fixture-v0"), where it leans
    with the prior so the demo UI has variety."""
    if model_version != "fixture-v0":
        return _evidence(ticket_id, "photo", "inconclusive", 1.0, 0.0, 1, {"stub": True, "reason": "photo verifier not built yet"})
    if prior >= 0.7:
        return _evidence(ticket_id, "photo", "contradicts_fix", 8.0, 0.5, 1, {"stub": True})
    return _evidence(ticket_id, "photo", "supports_fix", 0.3, 0.5, 1, {"stub": True})


def stub_citizen(ticket_id: str) -> dict[str, Any]:
    """STUB: no reply yet. Silence is weak evidence (LR 1.2), never satisfaction."""
    return _evidence(ticket_id, "citizen", "inconclusive", 1.2, 0.1, 2, {"stub": True, "reply": None})


def stub_human(ticket_id: str) -> dict[str, Any]:
    return _evidence(ticket_id, "human", "inconclusive", 1.0, 0.0, 10, {"stub": True, "status": "queued"})


def load_fixture(name: str) -> Any:
    return json.loads((config.CONTRACT_DIR / name).read_text(encoding="utf-8"))
