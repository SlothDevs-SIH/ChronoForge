import pytest

from app import agent, approvals, audit, config, fusion, planner, tools
from app.db import get_conn
from app.models import Evidence


def ev(check, lr):
    return Evidence(ticket_id="t", check=check, verdict="inconclusive", likelihood_ratio=lr, confidence=0.5)


def ticket_with(truth_false: bool, satellite: bool | None = None) -> str:
    for i in range(500):
        tid = f"T-{i}"
        if tools.stub_truth_false(tid) != truth_false:
            continue
        if satellite is not None and tools.get_score(tid)[0].satellite_eligible != satellite:
            continue
        return tid
    raise AssertionError


# fusion ---------------------------------------------------------------
def test_fusion_matches_contract_rule():
    # logit(0.5)=0, ln(4)+ln(2)=ln(8) -> posterior 8/9
    assert fusion.fuse(0.5, [ev("satellite", 4.0), ev("human", 2.0)]) == pytest.approx(8 / 9)


def test_fusion_no_evidence_returns_prior():
    assert fusion.fuse(0.3, []) == pytest.approx(0.3)


def test_fusion_downweights_correlated_pair():
    plain = fusion.fuse(0.5, [ev("photo", 4.0), ev("satellite", 4.0)])
    corr = fusion.fuse(0.5, [ev("photo", 4.0), ev("citizen", 4.0)])
    assert corr < plain


def test_state_thresholds():
    assert fusion.state_for(0.75) == "likely_not_fixed"
    assert fusion.state_for(0.25) == "verified_fixed"
    assert fusion.state_for(0.5) == "cannot_tell"


# planner guard --------------------------------------------------------
def test_guard_rejects_ineligible_unaffordable_and_repeated():
    s = planner.PlanState(budget_left=2, satellite_eligible=False)
    assert not planner.validate_choice("check_satellite", s)[0]
    assert not planner.validate_choice("request_human_spot_check", s)[0]
    assert not planner.validate_choice("propose_action", s)[0]
    assert not planner.validate_choice("delete_everything", s)[0]
    s.used.add("check_photo")
    assert not planner.validate_choice("check_photo", s)[0]
    assert planner.validate_choice("ask_citizen", s)[0]


# audit ----------------------------------------------------------------
def test_audit_chain_detects_tampering():
    for i in range(3):
        audit.append("e", {"i": i})
    assert audit.verify()["ok"]
    get_conn().execute("UPDATE audit SET event='{\"type\":\"e\",\"i\":99}' WHERE idx=2")
    out = audit.verify()
    assert not out["ok"] and out["first_broken_idx"] == 2


# agent loop -----------------------------------------------------------
def test_agent_confirms_a_bad_closure_and_requires_approval():
    tid = ticket_with(True)
    run_id = agent.start_run(tid)
    v = agent.execute(run_id, delay=0)
    assert v.state == "likely_not_fixed" and v.recommended_action == "reopen" and v.requires_human
    pending = approvals.list_approvals("pending")
    assert len(pending) == 1 and pending[0]["verdict_snapshot"]["ticket_id"] == tid
    assert agent.RUNS[run_id].events[-1].type == "approval_needed"


def test_agent_confirms_a_real_fix_without_action():
    tid = ticket_with(False, satellite=True)
    v = agent.execute(agent.start_run(tid), delay=0)
    assert v.state == "verified_fixed" and v.recommended_action == "none"
    assert approvals.list_approvals("pending") == []


def test_agent_abstains_when_budget_cannot_resolve_it():
    # a genuine fix with no satellite: photo+citizen alone may not clear 0.25, and the human check (10) is unaffordable
    for i in range(500):
        tid = f"T-{i}"
        if not tools.stub_truth_false(tid) and not tools.get_score(tid)[0].satellite_eligible                 and tools.get_score(tid)[0].p_false_closure >= 0.70:
            v = agent.execute(agent.start_run(tid), delay=0)
            assert v.state == "cannot_tell" and v.recommended_action == "human_spot_check" and v.requires_human
            assert approvals.list_approvals("pending") == []
            return
    raise AssertionError("no suitable ticket found")


def test_agent_never_exceeds_budget_or_step_cap():
    for i in range(30):
        run_id = agent.start_run(f"X-{i}")
        agent.execute(run_id, delay=0)
        run = agent.RUNS[run_id]
        assert run.cost_spent <= config.BUDGET
        assert run.step < 60
        assert run.events[-1].budget_left >= 0 or run.events[-1].type == "approval_needed"


def test_trace_events_match_contract_fields():
    run_id = agent.start_run("T-contract")
    agent.execute(run_id, delay=0)
    e = agent.RUNS[run_id].events[0].model_dump()
    assert set(e) == {"run_id", "step", "type", "tool", "summary", "cost_spent", "budget_left", "ts"}


def test_bad_planner_choice_is_rejected_by_guard():
    run_id = agent.start_run("T-guard")
    agent.execute(run_id, planner=lambda s: ("request_human_spot_check" if s.budget_left < 10 else "check_photo", "x"),
                  delay=0)
    run = agent.RUNS[run_id]
    assert run.cost_spent <= config.BUDGET


# approvals ------------------------------------------------------------
def test_approve_records_prediction_and_outcome_check():
    tid = ticket_with(True)
    agent.execute(agent.start_run(tid), delay=0)
    a = approvals.list_approvals()[0]
    out = approvals.decide(a["approval_id"], "approve", "looks right")
    assert out["status"] == "approved"
    assert out["engine_result"]["ok"] is False        # engine is down in tests; recorded, not hidden
    observed = approvals.run_outcome_check(a["approval_id"])
    assert "rerun_state" in observed
    row = approvals.outcomes()[0]
    assert row["predicted"] == "likely_not_fixed" and row["observed"]


def test_reject_stores_reason_and_cannot_decide_twice():
    agent.execute(agent.start_run(ticket_with(True)), delay=0)
    a = approvals.list_approvals()[0]
    out = approvals.decide(a["approval_id"], "reject", "officer visited")
    assert out["status"] == "rejected" and out["note"] == "officer visited"
    with pytest.raises(ValueError):
        approvals.decide(a["approval_id"], "approve")


def test_audit_chain_ok_after_full_run():
    agent.execute(agent.start_run(ticket_with(True)), delay=0)
    approvals.decide(approvals.list_approvals()[0]["approval_id"], "reject", "x")
    assert audit.verify()["ok"]
