"""Persisted verification runs, the versioned config, and the rule that nothing is invented."""
import pytest

from app import agent, approvals, config, tools
from app.db import get_conn
from app.models import Evidence, Score
from tests.authkit import bearer, link, seed_user
from tests.test_core import ticket_with

# ---- the v1 numbers, written out here independently of verification_config.json ----------------------------------------
V1 = {
    "version": "v1", "calibrated": False,
    "thresholds": {"not_fixed": 0.75, "fixed": 0.25}, "budget": 10, "max_steps": 8,
    "tool_costs": {"get_score": 0, "check_photo": 1, "check_satellite": 3, "ask_citizen": 2,
                   "request_human_spot_check": 10, "propose_action": 0},
    "correlation": {"pairs": [["photo", "citizen"]], "weight": 0.7},
    "photo": {"lr_duplicate": 8.0, "lr_gps_far": 4.0, "lr_stale": 3.0, "lr_clean": 0.5, "dup_hamming": 6,
              "gps_far_metres": 300.0, "stale_days": 30, "lr_scene": 5.0, "lr_before_after": 3.0, "lr_same_scene": 3.0},
    "citizen": {"lr_no": 6.0, "lr_partly": 2.0, "lr_yes": 0.3, "lr_silence": 1.2},
    "clip": {"scene_still_broken": 0.65, "different_place": 0.55, "lr_scene_broken": 5.0, "lr_different_place": 3.0},
    "dino": {"different_scene": 0.35},
    "stub_lr": {"photo": {"bad": 5.0, "good": 0.4}, "satellite": {"bad": 4.0, "good": 0.35},
                "citizen": {"bad": 6.0, "good": 0.3}, "human": {"bad": 20.0, "good": 0.05}},
}


def test_config_file_holds_exactly_the_v1_numbers():
    vc = {k: v for k, v in config.VC.items() if k not in ("note", "satellite_reference")}
    assert vc == V1
    assert config.CONFIG_VERSION == "v1" and config.CALIBRATED is False
    assert config.VC["satellite_reference"]["change_seen"] == 0.45 and config.VC["satellite_reference"]["no_change_seen"] == 1.25


def test_code_reads_the_same_numbers_the_file_holds():
    from app import citizen, clip_check, dino_check, photo
    assert (config.THRESH_NOT_FIXED, config.THRESH_FIXED, config.BUDGET, config.MAX_STEPS) == (0.75, 0.25, 10, 8)
    assert config.TOOL_COSTS == V1["tool_costs"]
    assert config.CORRELATED_PAIRS == [{"photo", "citizen"}] and config.CORRELATION_WEIGHT == 0.7
    assert (citizen.LR_NO, citizen.LR_PARTLY, citizen.LR_YES, citizen.LR_SILENCE) == (6.0, 2.0, 0.3, 1.2)
    assert (photo.LR_DUPLICATE, photo.LR_GPS_FAR, photo.LR_STALE, photo.LR_CLEAN) == (8.0, 4.0, 3.0, 0.5)
    assert (photo.DUP_HAMMING, photo.GPS_FAR_METRES, photo.STALE_DAYS) == (6, 300.0, 30)
    assert (clip_check.SCENE_STILL_BROKEN, clip_check.DIFFERENT_PLACE) == (0.65, 0.55)
    assert (clip_check.LR_SCENE_BROKEN, clip_check.LR_DIFFERENT_PLACE) == (5.0, 3.0)
    assert dino_check.DIFFERENT_SCENE == 0.35
    bad = next(t for t in (f"T-{i}" for i in range(50)) if tools.stub_truth_false(t))
    good = next(t for t in (f"T-{i}" for i in range(50)) if not tools.stub_truth_false(t))
    assert [tools.check_photo(bad).likelihood_ratio, tools.check_photo(good).likelihood_ratio] == [5.0, 0.4]
    assert [tools.check_satellite(bad, True).likelihood_ratio, tools.check_satellite(good, True).likelihood_ratio] == [4.0, 0.35]
    assert [tools.ask_citizen(bad).likelihood_ratio, tools.ask_citizen(good).likelihood_ratio] == [6.0, 0.3]
    assert [tools.request_human_spot_check(bad).likelihood_ratio, tools.request_human_spot_check(good).likelihood_ratio] == [20.0, 0.05]


# ---- helpers -----------------------------------------------------------------------------------------------------
def run_and_record(ticket_id: str) -> dict:
    run_id = agent.start_run(ticket_id)
    agent.execute(run_id, delay=0)
    row = get_conn().execute("SELECT record FROM verification_runs WHERE run_id=?", (run_id,)).fetchone()
    import json
    return json.loads(row["record"])


def stable(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if k not in ("run_id", "created_at")}


@pytest.fixture
def staff(client):
    seed_user("u_officer", "officer")
    return bearer("u_officer")


# (a) a clear success --------------------------------------------------------------------------------------------------
def test_a_clear_fix_is_recorded_with_its_checks_and_is_deterministic():
    tid = next(t for t in (f"T-{i}" for i in range(300)) if not tools.stub_truth_false(t)
               and run_and_record(t)["verification_verdict"] == "verified_fixed")
    rec = run_and_record(tid)
    assert rec["verification_verdict"] == "verified_fixed" and rec["status"] == "done"
    assert rec["config_version"] == "v1" and rec["calibrated"] is False
    assert "not measured on real closures" in rec["note"]
    assert rec["closure_claimed"] == "unknown"          # stub mode never reads the city's record, so it says so
    assert rec["provenance"]["prior_source"] == "stub" and rec["provenance"]["data_quality"] is None
    assert {c["check"] for c in rec["checks"]} == {"photo", "satellite", "citizen", "human"}
    performed = [c for c in rec["checks"] if c["performed"]]
    assert performed and all(c["likelihood_ratio"] is not None and c["skipped_reason"] is None for c in performed)
    assert rec["posterior"] <= config.THRESH_FIXED
    assert stable(run_and_record(tid)) == stable(rec)    # same inputs, same record


# (b) satellite skipped ------------------------------------------------------------------------------------------------
def test_an_ineligible_satellite_check_is_skipped_with_a_reason_not_counted_as_evidence():
    tid = ticket_with(True, satellite=False)
    rec = run_and_record(tid)
    sat = next(c for c in rec["checks"] if c["check"] == "satellite")
    assert sat["performed"] is False and sat["skipped_reason"] == "not applicable to this ticket"
    assert sat["verdict"] is None and sat["likelihood_ratio"] is None
    assert rec["verification_verdict"] != "not_performed"              # the photo check did run
    assert any(c["performed"] for c in rec["checks"] if c["check"] == "photo")


def test_unavailable_imagery_is_skipped_never_evidence(monkeypatch):
    monkeypatch.setattr(config, "USE_STUBS", False)
    monkeypatch.setattr(tools, "get_score", lambda t: (Score(ticket_id=t, p_false_closure=0.6, satellite_eligible=True,
                                                             score_type="risk_rank_prior"), "engine"))
    monkeypatch.setattr(tools, "_get_ticket", lambda t: {"status": "closed", "data_quality": "real", "city": "mumbai"})
    monkeypatch.setattr(tools, "check_satellite", lambda t, e: Evidence(
        ticket_id=t, check="satellite", verdict="inconclusive", likelihood_ratio=1.0, confidence=0.0, cost=0,
        details={"abstain_reason": "cloud cover"}))
    monkeypatch.setattr(tools, "check_photo", lambda t, u=None: Evidence(
        ticket_id=t, check="photo", verdict="inconclusive", likelihood_ratio=1.0, confidence=0.0, cost=1,
        details={"reason": "no closure photo"}))
    rec = run_and_record("MUM-1")
    sat = next(c for c in rec["checks"] if c["check"] == "satellite")
    assert sat["performed"] is False and sat["skipped_reason"] == "cloud cover" and sat["likelihood_ratio"] is None
    assert rec["verification_verdict"] == "not_performed" and rec["posterior"] == rec["prior"] == 0.6   # imagery never moved it
    assert rec["provenance"] == {"data_quality": "real", "score_type": "risk_rank_prior", "city": "mumbai", "prior_source": "engine"}
    assert rec["closure_claimed"] == "closed"


# (c) every check skipped ---------------------------------------------------------------------------------------------
def test_when_every_check_is_skipped_the_verification_verdict_is_not_performed(monkeypatch):
    monkeypatch.setattr(config, "USE_STUBS", False)
    monkeypatch.setattr(tools, "get_score", lambda t: (Score(ticket_id=t, p_false_closure=0.5, satellite_eligible=False,
                                                             score_type="risk_rank_prior"), "engine"))
    monkeypatch.setattr(tools, "_get_ticket", lambda t: {"status": "closed", "data_quality": "real", "city": "bengaluru"})

    def skipped(check, why, cost=0):
        return Evidence(ticket_id="BLR-1", check=check, verdict="inconclusive", likelihood_ratio=1.0, confidence=0.0,
                        cost=cost, details={"reason": why})
    monkeypatch.setattr(tools, "check_photo", lambda t, u=None: skipped("photo", "no closure photo", 1))
    monkeypatch.setattr(tools, "ask_citizen", lambda t: skipped("citizen", "no usable contact"))
    rec = run_and_record("BLR-1")
    assert rec["verification_verdict"] == "not_performed" and not any(c["performed"] for c in rec["checks"])
    reasons = {c["check"]: c["skipped_reason"] for c in rec["checks"]}
    assert reasons == {"photo": "no closure photo", "satellite": "not applicable to this ticket",
                       "citizen": "no usable contact", "human": "not run"}   # the spot check costs 10: unaffordable after the photo
    assert rec["posterior"] == rec["prior"] == 0.5       # nothing was learned, nothing moved
    assert rec["calibrated"] is False


# a run that cannot happen --------------------------------------------------------------------------------------------
def test_engine_down_gives_a_pending_record_with_a_reason_and_no_numbers(client, staff, monkeypatch):
    monkeypatch.setattr(config, "USE_STUBS", False)        # real services expected, Engine unreachable (conftest port 9)
    run_id = agent.start_run("BLR-404")
    with pytest.raises(tools.EngineUnavailable):
        agent.execute(run_id, delay=0)
    got = client.get("/verification/BLR-404/latest", headers=staff).json()
    assert got["status"] == "pending" and got["verification_verdict"] == "not_performed"
    assert "cannot get a score" in got["pending_reason"]
    assert got["prior"] is None and got["posterior"] is None and got["checks"] == []
    assert got["calibrated"] is False and got["config_version"] == "v1" and got["review_state"] == "none"


def test_a_ticket_with_no_run_is_pending_not_invented(client, staff):
    got = client.get("/verification/T-777/latest", headers=staff).json()
    assert got["status"] == "pending" and got["run_id"] is None and got["verification_verdict"] == "not_performed"
    assert "No verification has been run" in got["pending_reason"]
    assert client.get("/verification/T-777", headers=staff).json() == []


# the three states stay separate ----------------------------------------------------------------------------------------
def test_review_state_follows_the_human_decision_while_the_engine_verdict_stays_put(client, staff):
    tid = ticket_with(True, satellite=True)
    rec = run_and_record(tid)
    assert rec["verification_verdict"] == "likely_not_fixed"
    live = client.get(f"/verification/{tid}/latest", headers=staff).json()
    assert live["review_state"] == "pending" and live["closure_claimed"] == "unknown"
    pending = approvals.list_approvals("pending")[0]
    client.post(f"/approvals/{pending['approval_id']}/decide", headers=staff, json={"decision": "reject", "note": "checked"})
    after = client.get(f"/verification/{tid}/latest", headers=staff).json()
    assert after["review_state"] == "rejected" and after["verification_verdict"] == "likely_not_fixed"
    assert after["posterior"] == live["posterior"]


def test_a_linked_citizen_can_read_their_ticket_record_and_nobody_elses(client, staff):
    seed_user("u_cit")
    link("u_cit", "T-0")
    run_and_record("T-0")
    run_and_record("T-1")
    h = bearer("u_cit")
    assert client.get("/verification/T-0/latest", headers=h).json()["ticket_id"] == "T-0"
    assert client.get("/verification/T-1/latest", headers=h).status_code == 403
    assert len(client.get("/verification/T-0", headers=h).json()) == 1
