"""Module 2: the agent loop. Hand-written, no framework. The planner is pluggable (deterministic now,
LLM-chosen later); every choice passes planner.validate_choice before a tool runs."""
import json
import threading
import time
from typing import Callable
from uuid import uuid4

from . import approvals, audit, config, events, fusion, tools
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
MAX_RUNS_IN_MEMORY = 300


def start_run(ticket_id: str) -> str:
    if len(RUNS) >= MAX_RUNS_IN_MEMORY:   # finished runs stay readable from the database; drop the oldest in memory
        for old in [k for k, r in RUNS.items() if r.status != "running"][: len(RUNS) - MAX_RUNS_IN_MEMORY + 1]:
            RUNS.pop(old, None)
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


def default_planner() -> Planner:
    if config.USE_LLM_PLANNER:
        from .llm_planner import llm_planner
        return llm_planner
    return choose_next


def execute(run_id: str, planner: Planner | None = None, delay: float | None = None) -> Verdict:
    run = RUNS[run_id]
    planner = planner or default_planner()
    delay = config.STEP_DELAY if delay is None else delay
    try:
        score, source = tools.get_score(run.ticket_id)
        run.emit("tool_call", f"get_score -> {score.p_false_closure:.2f} (source: {source})", "get_score")
        prior = score.p_false_closure
        posterior = prior
        state = PlanState(budget_left=config.BUDGET, satellite_eligible=score.satellite_eligible,
                          prior=prior, posterior=posterior)

        for stored in _answered_citizen_evidence(run.ticket_id):
            state.used.add("ask_citizen")
            run.evidence.append(stored)
            posterior = fusion.fuse(prior, run.evidence)
            state.posterior, state.evidence = posterior, run.evidence
            run.emit("tool_result", f"citizen reply on file: {stored.verdict.replace('_', ' ')}, "
                                    f"LR {stored.likelihood_ratio:g}; posterior {posterior:.2f}", "ask_citizen")

        steps = 0
        # contract: the score alone never gives a verdict, so keep checking until one check is conclusive
        while (fusion.is_uncertain(posterior) or not _conclusive(run.evidence)
               or _photo_gate_open(posterior, state)) and steps < config.MAX_STEPS:
            steps += 1
            if _photo_gate_open(posterior, state):   # never confirm a fix on one answer: look at the closure photo
                tool, why = "check_photo", "a closure is never confirmed as fixed without checking its photo (cost 1)"
            else:
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
            state.posterior, state.evidence = posterior, run.evidence
            run.emit("tool_result", f"{CHECK_OF_TOOL[tool]}: {ev.verdict.replace('_', ' ')}, "
                                    f"LR {ev.likelihood_ratio:g}; posterior {posterior:.2f}", tool)

        st = fusion.state_for(posterior)
        if st != "cannot_tell" and not _conclusive(run.evidence):
            run.emit("thought", "no independent check was conclusive; the score alone cannot give a verdict")
            st = "cannot_tell"
        if st == "likely_not_fixed" and config.USE_SKEPTIC:
            from . import skeptic
            reply, info = skeptic.review(posterior, run.evidence)
            if reply is None:
                run.emit("thought", f"skeptic: {info}; verdict left as the evidence says")
            elif reply.hole_found:
                run.emit("thought", f"skeptic [{info}] found a weakness: {reply.argument} Downgrading to cannot_tell.")
                st = "cannot_tell"
            else:
                run.emit("thought", f"skeptic [{info}] found no hole: {reply.argument}")
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
            events.record(run.ticket_id, "reopen_proposed", "A reopen was proposed and is waiting for an administrator.", "staff")
        run.status = "done"
        try:   # tell the case tracker (citizen message, timeline); a failure here must never fail the run itself
            from . import cases
            cases.on_verdict(run.ticket_id, verdict)
        except Exception:
            pass
    except Exception as exc:  # surface failures in the trace instead of a silent dead stream
        run.status = "error"
        run.emit("thought", f"run failed: {exc}")
        raise
    finally:
        _persist_run(run)
    return verdict


def _photo_gate_open(posterior: float, state: PlanState) -> bool:
    """True when the evidence says 'fixed' but the cheap photo check has not run yet and is affordable."""
    return (posterior <= config.THRESH_FIXED and "check_photo" not in state.used
            and config.TOOL_COSTS["check_photo"] <= state.budget_left)


def _conclusive(evidence: list[Evidence]) -> bool:
    return any(e.verdict != "inconclusive" for e in evidence)


def _answered_citizen_evidence(ticket_id: str) -> list[Evidence]:
    rows = get_conn().execute("SELECT body FROM evidence WHERE ticket_id=? AND run_id IS NULL ORDER BY created_at",
                              (ticket_id,)).fetchall()
    out = [Evidence.model_validate_json(r["body"]) for r in rows]
    return [e for e in out if e.check == "citizen"][-1:]


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
