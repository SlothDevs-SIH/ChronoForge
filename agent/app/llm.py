"""Thin LLM interface: complete_json(prompt, schema) tries each configured provider in order.

Output is validated against a Pydantic model; invalid output gets one retry on the same provider,
then the next provider. If every provider fails, LLMError is raised and the caller falls back to the
deterministic planner. Keys come from the environment only. Prompts must carry hashes, never raw
phone numbers or officer identifiers.
"""
import json
import logging
from typing import Callable, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from . import config

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    pass


def _gemini(prompt: str) -> str:
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent",
        headers={"x-goog-api-key": config.GEMINI_API_KEY},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"responseMimeType": "application/json", "temperature": 0}},
        timeout=config.LLM_TIMEOUT)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _openai(prompt: str) -> str:
    r = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
        json={"model": config.OPENAI_MODEL, "temperature": 0,
              "response_format": {"type": "json_object"},
              "messages": [{"role": "user", "content": prompt}]},
        timeout=config.LLM_TIMEOUT)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


PROVIDERS: dict[str, Callable[[str], str]] = {"gemini": _gemini, "openai": _openai}
_KEY = {"gemini": lambda: config.GEMINI_API_KEY, "openai": lambda: config.OPENAI_API_KEY}


def available_providers() -> list[str]:
    """Configured providers (in .env order) that have a key (or are injected, e.g. in tests)."""
    return [p for p in config.LLM_PROVIDERS if p in PROVIDERS and (p not in _KEY or _KEY[p]())]


def complete_json(prompt: str, schema: type[T]) -> tuple[T, str]:
    """Return (validated object, provider name). Raises LLMError when nothing usable came back."""
    full = (f"{prompt}\n\nRespond with a single JSON object matching this JSON schema, no prose:\n"
            f"{json.dumps(schema.model_json_schema())}")
    errors: list[str] = []
    for name in available_providers():
        for attempt in (1, 2):   # one retry on invalid output
            try:
                raw = PROVIDERS[name](full)
                return schema.model_validate_json(raw), name
            except (ValidationError, ValueError) as exc:
                errors.append(f"{name}#{attempt}: invalid output ({type(exc).__name__})")
            except Exception as exc:   # network, auth, rate limit: no point retrying this provider
                errors.append(f"{name}: {type(exc).__name__}")
                break
    raise LLMError("; ".join(errors) or "no LLM provider configured")
