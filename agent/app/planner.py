"""Deterministic planner and the guard that any planner (including a future LLM one) must pass."""
from dataclasses import dataclass, field
from . import config

# cheap first; satellite only when eligible; human spot check last (cost 10)
PREFERENCE = ["check_photo", "ask_citizen", "check_satellite", "request_human_spot_check"]

CHECK_OF_TOOL = {"check_photo": "photo", "ask_citizen": "citizen",
                 "check_satellite": "satellite", "request_human_spot_check": "human"}


@dataclass
class PlanState:
    budget_left: int
    satellite_eligible: bool
    used: set[str] = field(default_factory=set)   # tool names already called this run
    prior: float = 0.5
    posterior: float = 0.5
    evidence: list = field(default_factory=list)  # Evidence collected so far


def eligible_tools(state: PlanState) -> list[str]:
    out = []
    for t in PREFERENCE:
        if t in state.used:
            continue
        if config.TOOL_COSTS[t] > state.budget_left:
            continue
        if t == "check_satellite" and not state.satellite_eligible:
            continue
        out.append(t)
    return out


def validate_choice(tool: str, state: PlanState) -> tuple[bool, str]:
    """Code-level guard: the planner cannot pick an unknown, ineligible, repeated or unaffordable tool."""
    if tool not in config.TOOL_COSTS or tool in ("get_score", "propose_action"):
        return False, f"{tool} is not a selectable check"
    if tool in eligible_tools(state):
        return True, "ok"
    if tool in state.used:
        return False, f"{tool} already used"
    if config.TOOL_COSTS[tool] > state.budget_left:
        return False, f"{tool} costs {config.TOOL_COSTS[tool]}, only {state.budget_left} left"
    return False, f"{tool} is not eligible for this ticket"


def choose_next(state: PlanState) -> tuple[str | None, str]:
    cands = eligible_tools(state)
    if not cands:
        return None, "no affordable eligible check remains"
    tool = cands[0]
    return tool, f"cheapest eligible check not yet run is {tool} (cost {config.TOOL_COSTS[tool]})"
