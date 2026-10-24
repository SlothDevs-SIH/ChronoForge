"""Module 2: the agent loop. Hand-written, no framework. The planner is pluggable (deterministic now,
LLM-chosen later); every choice passes planner.validate_choice before a tool runs."""
import json
import threading
import time
from typing import Callable
from uuid import uuid4

from . import approvals, audit, config, fusion, tools
from .db import get_conn, lock
from .models import Evidence, TraceEvent, Verdict, now_iso
from .planner import CHECK_OF_TOOL, PlanState, choose_next, validate_choice

Planner = Callable[[PlanState], tuple[str | None, str]]


class RunState:
    def __init__(self, run_id: str, ticket_id: str):
        self.run_id, self.ticket_id = run_id, ticket_id
        self.events: list[TraceEvent] = []
        self.status = "running"
        self.verdict: Verdict | None = None
        self.evidence: list[Evidence] = []
        self.cost_spent = 0
        self.step = 0

    def emit(self, type_: str, summary: str, tool: str | None = None) -> TraceEvent:
        self.step += 1
        ev = TraceEvent(run_id=self.run_id, step=self.step, type=type_, tool=tool, summary=summary,
                        cost_spent=self.cost_spent, budget_left=config.BUDGET - self.cost_spent)
        self.events.append(ev)
        audit.append("trace", ev.model_dump())
        return ev


RUNS: dict[str, RunState] = {}


def start_run(ticket_id: str) -> str:
    run_id = str(uuid4())
    RUNS[run_id] = RunState(run_id, ticket_id)
    with lock():
        get_conn().execute("INSERT INTO runs (run_id, ticket_id, status, created_at) VALUES (?,?,?,?)",
                           (run_id, ticket_id, "running", now_iso()))
        get_conn().commit()
    audit.append("run_started", {"run_id": run_id, "ticket_id": ticket_id})
    return run_id


def _explain(state: str, prior: float, post: float, evidence: list[Evidence]) -> str:
    parts = [f"{e.check} check: {e.verdict.replace('_', ' ')} (LR {e.likelihood_ratio:g})" for e in evidence]
    body = "; ".join(parts) if parts else "no independent checks were run"
    head = {"verified_fixed": "The closure looks genuine.",
            "likely_not_fixed": "The closure is probably false.",
            "cannot_tell": "The evidence is not strong enough either way."}[state]
    return f"{head} Probability of a false closure moved from {prior:.0%} to {post:.0%}. {body}."


def execute(run_id: str, planner: Planner = choose_next, delay: float | None = None) -> Verdict:
    run = RUNS[run_id]
    delay = config.STEP_DELAY if delay is None else delay
    try:
        score, source = tools.get_score(run.ticket_id)
        run.emit("tool_call", f"get_score -> {score.p_false_closure:.2f} (source: {source})", "get_score")
        prior = score.p_false_closure
        posterior = prior
        state = PlanState(budget_left=config.BUDGET, satellite_eligible=score.satellite_eligible)

        steps = 0
        while fusion.is_uncertain(posterior) and steps < config.MAX_STEPS:
            steps += 1
            tool, why = planner(state)
            if tool is None:
                run.emit("thought", why)
                break
            ok, reason = validate_choice(tool, state)
            if not ok:
                run.emit("thought", f"planner chose {tool} but guard rejected it: {reason}")
                break
            run.emit("thought", why)
            run.emit("tool_call", f"calling {tool}", tool)
            time.sleep(delay)
            if tool == "check_photo":
                ev = tools.check_photo(run.ticket_id)
            elif tool == "ask_citizen":
                ev = tools.ask_citizen(run.ticket_id)
            elif tool == "check_satellite":
                ev = tools.check_satellite(run.ticket_id, score.satellite_eligible)
            else:
                ev = tools.request_human_spot_check(run.ticket_id)
            state.used.add(tool)
            state.budget_left -= ev.cost
            run.cost_spent += ev.cost
            run.evidence.append(ev)
            _store_evidence(ev, run_id)
            audit.append("tool_result", {"run_id": run_id, "tool": tool, "evidence_id": ev.evidence_id,
                                         "check": ev.check, "verdict": ev.verdict, "lr": ev.likelihood_ratio})
            posterior = fusion.fuse(prior, run.evidence)
            run.emit("tool_result", f"{CHECK_OF_TOOL[tool]}: {ev.verdict.replace('_', ' ')}, "
                                    f"LR {ev.likelihood_ratio:g}; posterior {posterior:.2f}", tool)

        st = fusion.state_for(posterior)
        action = {"likely_not_fixed": "reopen", "cannot_tell": "human_spot_check", "verified_fixed": "none"}[st]
        verdict = Verdict(ticket_id=run.ticket_id, state=st, prior=round(prior, 4), posterior=round(posterior, 4),
                          evidence_ids=[e.evidence_id for e in run.evidence], recommended_action=action,
                          requires_human=action != "none", explanation=_explain(st, prior, posterior, run.evidence))
        run.verdict = verdict
        run.emit("verdict", f"{st}: {verdict.explanation}")
        audit.append("verdict", {"run_id": run_id, **verdict.model_dump()})
        if st == "likely_not_fixed":
            approval = approvals.propose_action(run.ticket_id, run_id, "reopen", verdict)
            run.emit("approval_needed", f"reopen proposed, awaiting human approval {approval['approval_id']}",
                     "propose_action")
        run.status = "done"
    except Exception as exc:  # surface failures in the trace instead of a silent dead stream
        run.status = "error"
        run.emit("thought", f"run failed: {exc}")
        raise
    finally:
        _persist_run(run)
    return verdict


def _store_evidence(ev: Evidence, run_id: str) -> None:
    with lock():
        get_conn().execute("INSERT INTO evidence VALUES (?,?,?,?,?)",
                           (ev.evidence_id, ev.ticket_id, run_id, ev.model_dump_json(), ev.created_at))
        get_conn().commit()


def _persist_run(run: RunState) -> None:
    with lock():
        get_conn().execute("UPDATE runs SET status=?, verdict=?, trace=? WHERE run_id=?",
                           (run.status, run.verdict.model_dump_json() if run.verdict else None,
                            json.dumps([e.model_dump() for e in run.events]), run.run_id))
        get_conn().commit()


def run_in_background(run_id: str) -> None:
    threading.Thread(target=lambda: _safe(run_id), daemon=True).start()


def _safe(run_id: str) -> None:
    try:
        execute(run_id)
    except Exception:
        pass
