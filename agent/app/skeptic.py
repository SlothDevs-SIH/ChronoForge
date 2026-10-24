"""Optional second opinion (Q9 stretch): after the agent says "likely not fixed", one LLM call argues why the
closure might be real. The verdict stands only if the skeptic finds no hole; otherwise it is downgraded to
cannot_tell and routed to a human spot check. Fails open to "no hole found" being unknown, never to a silent
upgrade: if the LLM is unavailable the verdict is left as the evidence says, and the trace records that."""
from pydantic import BaseModel

from . import llm
from .models import Evidence


class SkepticReply(BaseModel):
    hole_found: bool
    argument: str   # one or two sentences


def review(posterior: float, evidence: list[Evidence]) -> tuple[SkepticReply | None, str]:
    """Return (reply, provider) or (None, reason) when the LLM is unavailable."""
    seen = "; ".join(f"{e.check}: {e.verdict}, LR {e.likelihood_ratio:g}, confidence {e.confidence:g}"
                     for e in evidence) or "none"
    prompt = (
        "You are a skeptic reviewing an automated finding that a municipal complaint was falsely marked as "
        f"fixed (probability {posterior:.2f}). Evidence: {seen}.\n"
        "Argue the strongest case that the closure might actually be genuine. Set hole_found to true only if "
        "the evidence has a real weakness (weak, stale, unreliable, correlated, or only one source); "
        "otherwise false.")
    try:
        reply, provider = llm.complete_json(prompt, SkepticReply)
    except llm.LLMError as exc:
        return None, f"skeptic unavailable: {exc}"
    return reply, provider
