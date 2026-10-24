"""LLM tool-chooser. AYUSH: implement the provider calls. Everything here must be optional.

Contract with the planner:
  choose_tool(state) -> a tool name string, or None.
The planner validates the answer (eligibility, budget, not-already-used) and falls back to the
deterministic planner on None, an invalid answer, or any exception. Never let this raise past the planner.

Provider order comes from config.LLM_PROVIDERS (default gemini, openai). Keys live in .env only.
Log which provider answered each step; the planner puts it in the trace summary.
Strict JSON only: ask for {"tool": "<name>", "reason": "<short>"} and validate with Pydantic.
"""
import os
from typing import Any, Optional

from . import config


class ProviderNotConfigured(Exception):
    pass


async def _call_gemini(prompt: str) -> dict[str, Any]:
    if not os.environ.get("GEMINI_API_KEY"):
        raise ProviderNotConfigured("GEMINI_API_KEY missing")
    raise NotImplementedError("TODO: Google AI Studio call, JSON mode")


async def _call_openai(prompt: str) -> dict[str, Any]:
    if not os.environ.get("OPENAI_API_KEY"):
        raise ProviderNotConfigured("OPENAI_API_KEY missing")
    raise NotImplementedError("TODO: OpenAI call, JSON mode")


_PROVIDERS = {"gemini": _call_gemini, "openai": _call_openai}


async def choose_tool(state: dict[str, Any]) -> Optional[dict[str, str]]:
    """Return {"tool": ..., "provider": ..., "reason": ...} or None to use the deterministic planner."""
    if not config.USE_LLM:
        return None
    prompt = f"Pick the next verification tool for this closed complaint. State: {state}"
    for name in config.LLM_PROVIDERS:
        try:
            out = await _PROVIDERS[name](prompt)
            return {"tool": str(out["tool"]), "provider": name, "reason": str(out.get("reason", ""))}
        except Exception:
            continue
    return None
