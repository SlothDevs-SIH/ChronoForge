"""LLM-chosen next tool (Q9 option B). The LLM only proposes; planner.validate_choice enforces eligibility
and budget, and any failure (no key, bad JSON, rejected choice) falls back to the deterministic planner.
The prompt carries scores and check names only: no ticket text, phone numbers or officer identifiers."""
from pydantic import BaseModel

from . import config, llm
from .planner import PlanState, choose_next, eligible_tools, validate_choice


class Choice(BaseModel):
    tool: str     # one of the offered tool names, or "stop"
    reason: str   # one short sentence


def _prompt(state: PlanState, options: list[str]) -> str:
    seen = "; ".join(f"{e.check}: {e.verdict} (LR {e.likelihood_ratio:g})" for e in state.evidence) or "none yet"
    menu = "\n".join(f"- {t} (cost {config.TOOL_COSTS[t]})" for t in options)
    return (
        "You are an investigator deciding how to verify whether a municipal complaint was really fixed.\n"
        f"Prior probability the closure is false: {state.prior:.2f}. Current probability: {state.posterior:.2f}.\n"
        f"Budget left: {state.budget_left}. Evidence so far: {seen}.\n"
        f"Choose the single most informative next check per unit cost from:\n{menu}\n"
        "Prefer cheap checks first. Answer \"stop\" only if more evidence is unlikely to change the decision.")


def llm_planner(state: PlanState) -> tuple[str | None, str]:
    options = eligible_tools(state)
    if not options:
        return choose_next(state)
    try:
        choice, provider = llm.complete_json(_prompt(state, options), Choice)
    except llm.LLMError as exc:
        tool, why = choose_next(state)
        return tool, f"[fallback: deterministic planner; LLM unavailable: {exc}] {why}"
    if choice.tool == "stop":
        return None, f"[{provider}] {choice.reason}"
    ok, reason = validate_choice(choice.tool, state)
    if not ok:
        tool, why = choose_next(state)
        return tool, f"[fallback: guard rejected {provider} choice: {reason}] {why}"
    return choice.tool, f"[{provider}] {choice.reason}"


class _Intent(BaseModel):
    intent: str   # yes | no | partly | unclear


def classify_reply(text: str) -> str | None:
    """Zero-shot fallback for free-text citizen replies the keyword map could not read (Hinglish, Marathi,
    Kannada). Returns 'yes' | 'no' | 'partly' or None."""
    try:
        out, _ = llm.complete_json(
            "A citizen was asked whether a reported street problem was fixed. Classify their reply as one of "
            f"yes, no, partly, unclear. Reply text (any language): {text[:500]!r}", _Intent)
    except llm.LLMError:
        return None
    return out.intent if out.intent in ("yes", "no", "partly") else None
