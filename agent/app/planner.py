"""Budgeted agent loop.

1. posterior <- engine prior. 2. While no independent evidence exists yet, or the posterior is uncertain, and budget remains: pick the next tool
(LLM choice if enabled and valid, else the deterministic preference order), run it, fuse its LR.
3. Threshold into a verdict. The planner never acts: a not-fixed verdict only *recommends* an action,
and main.py turns that into a human approval item.
"""
import asyncio
from typing import Any, Awaitable, Callable, Optional

from . import config, fusion, llm, tools
from .tools import Engine

ORDER = ["check_photo", "check_satellite", "ask_citizen", "request_human_spot_check"]
OnEvent = Callable[[dict[str, Any]], None]


def eligible(tool: str, st: dict[str, Any]) -> bool:
    if tool in st["used"] or config.TOOL_COST[tool] > st["budget_left"]:
        return False
    if tool == "check_satellite" and not st["satellite_eligible"]:
        return False
    return True


def deterministic_choice(st: dict[str, Any]) -> Optional[str]:
    return next((t for t in ORDER if eligible(t, st)), None)


async def choose(st: dict[str, Any]) -> tuple[Optional[str], str]:
    """Returns (tool, note). Invalid or failed LLM answers fall back to the deterministic planner."""
    try:
        pick = await llm.choose_tool({k: st[k] for k in ("posterior", "budget_left", "used", "satellite_eligible")})
    except Exception:
        pick = None
    if pick and pick["tool"] in config.TOOL_COST and eligible(pick["tool"], st):
        return pick["tool"], f"{pick['provider']}: {pick['reason']}"
    return deterministic_choice(st), "deterministic planner"


def _explain(score: dict, evidence: list[dict]) -> str:
    parts = [f"{r['feature']}={r['value']}" for r in score["reasons"][:2]]
    parts += [f"{e['check']} check {e['verdict'].replace('_', ' ')}" for e in evidence if e["verdict"] != "inconclusive"]
    return "Signals: " + "; ".join(parts) if parts else "No decisive signal."


async def run_agent(run_id: str, ticket_id: str, engine: Engine, on_event: OnEvent, budget: int = config.BUDGET) -> dict[str, Any]:
    step = 0

    def emit(type_: str, tool: Optional[str], summary: str, spent: int, left: int) -> None:
        nonlocal step
        step += 1
        on_event({"run_id": run_id, "step": step, "type": type_, "tool": tool, "summary": summary,
                  "cost_spent": spent, "budget_left": left})

    score = await engine.get_score(ticket_id)
    prior = score["p_false_closure"]
    st: dict[str, Any] = {"used": set(), "budget_left": budget, "posterior": prior,
                          "satellite_eligible": score["satellite_eligible"]}
    spent, evidence = 0, []
    emit("tool_call", "get_score", f"Prior false-closure probability {prior:.2f}", spent, st["budget_left"])

    if not score["satellite_eligible"]:
        emit("tool_result", "check_satellite", "Skipped: not checkable from orbit (cost 0)", spent, st["budget_left"])

    steps = 0
    # The score alone never yields a verdict: at least one independent check must run first.
    while (not evidence or fusion.is_uncertain(st["posterior"])) and steps < config.MAX_STEPS:
        tool, note = await choose(st)
        if tool is None:
            break
        steps += 1
        await asyncio.sleep(config.STEP_DELAY_S)
        if tool == "check_photo":
            ev = tools.stub_photo(ticket_id, prior)
        elif tool == "check_satellite":
            ev = await engine.satellite_check(ticket_id)
        elif tool == "ask_citizen":
            ev = tools.stub_citizen(ticket_id)
        else:
            ev = tools.stub_human(ticket_id)
        evidence.append(ev)
        st["used"].add(tool)
        spent += ev["cost"]
        st["budget_left"] = budget - spent
        st["posterior"] = fusion.fuse(prior, [e["likelihood_ratio"] for e in evidence])
        emit("tool_call", tool, f"{ev['verdict']} (LR {ev['likelihood_ratio']:g}); posterior {st['posterior']:.2f} [{note}]",
             spent, st["budget_left"])

    state = fusion.verdict_state(st["posterior"])
    action = {"likely_not_fixed": "reopen", "cannot_tell": "human_spot_check", "verified_fixed": "none"}[state]
    verdict = {
        "ticket_id": ticket_id, "state": state, "prior": prior, "posterior": st["posterior"],
        "evidence_ids": [e["evidence_id"] for e in evidence], "recommended_action": action,
        "requires_human": True, "explanation": _explain(score, evidence),
    }
    emit("verdict", None, f"{state}, posterior {st['posterior']:.2f}", spent, st["budget_left"])
    return {"verdict": verdict, "evidence": evidence}
