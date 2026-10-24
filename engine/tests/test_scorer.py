"""Scorer tests. Small built-in frames, no raw data needed. Several guard bugs found while building the scorer."""
import numpy as np
import pandas as pd
import pytest

from app.models import Ticket
from app.scorer import core, features_bengaluru as fb, features_mumbai as fm, features_synthetic as fs
from app.scoring import from_row

DAY = 86400


# ---- time handling (a real bug: astype(int64)//1e9 gave units of 1000 s and silently made every window decades long) ----
def test_epoch_seconds_is_really_seconds():
    s = pd.to_datetime(pd.Series(["2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z"]), utc=True)
    assert list(core.epoch_seconds(s)) == [1704067200, 1704067200 + DAY]


def test_prior_counts_respect_the_window():
    ts = np.array([0, 10 * DAY, 25 * DAY, 40 * DAY, 41 * DAY])
    key = pd.Series(["a"] * 5)
    # earlier rows only. 30-day window: day 40 sees day 10 (exactly 30 d back, inside) and day 25 but not day 0;
    # day 41 sees day 25 and day 40 but not day 10 (31 d back).
    assert list(fb._prior_counts(ts, [key], 30)) == [0, 1, 2, 2, 2]
    # 14-day window: day 10 sees day 0; day 25 sees nothing (day 10 is 15 d back); day 40 sees nothing; day 41 sees day 40.
    assert list(fb._prior_counts(ts, [key], 14)) == [0, 1, 0, 0, 1]


def test_lagged_rate_does_not_use_recent_outcomes():
    ts = np.array([0, 5 * DAY, 40 * DAY])
    y = np.array([1, 1, 0])
    cap = np.array([True, True, True])
    r = fb._lagged_rate(ts, y, cap, [pd.Series(["w"] * 3)], 30, base=0.1, alpha=1.0)
    assert r[0] == pytest.approx(0.1) and r[1] == pytest.approx(0.1)   # nothing is 30 days old yet
    assert r[2] == pytest.approx((2 + 0.1) / (2 + 1))                    # both earlier rows are old enough by day 40


def test_lagged_rate_ignores_the_structural_zero_period():
    ts = np.array([0, DAY, 100 * DAY])
    y = np.array([0, 0, 0])
    cap = np.array([False, False, True])
    r = fb._lagged_rate(ts, y, cap, [pd.Series(["w"] * 3)], 30, base=0.05, alpha=10.0)
    assert r[2] == pytest.approx(0.05)    # rows before the reopen mechanism existed are not counted as negatives


# ---- leakage rules for the Bengaluru label ----
def test_bengaluru_features_exclude_remark_and_staff_columns():
    names = fb.CAT_COLS + fb.NUM_COLS
    assert not [c for c in names if "staff" in c or "remark" in c or "role" in c]


def test_bengaluru_build_sorts_and_labels(tmp_path):
    rows = [{"ticket_id": f"t{i}", "created_at": f"2025-01-{i + 1:02d}T05:00:00Z", "status": st, "ward": "w", "text": "Potholes",
             "category": "pothole", "ward_zone": None, "closed_by_hash": "x"} for i, st in enumerate(["closed", "reopened", "closed"])]
    df, _ = fb.build(pd.DataFrame(rows[::-1]), base_rate=0.01)
    assert list(df["ticket_id"]) == ["t0", "t1", "t2"] and list(df["y"]) == [0, 1, 0]
    assert df["hour"].tolist() == [10, 10, 10]   # 05:00 UTC is 10:30 IST


# ---- Mumbai label: repeat in (closure + 24 h, closure + 14 d] ----
def _mumbai(created_hours_after_close):
    base = pd.Timestamp("2026-05-01T00:00:00Z")
    rows = [{"ticket_id": "orig", "created_at": base.isoformat(), "closed_at": (base + pd.Timedelta(hours=10)).isoformat(),
             "status": "closed", "h3": "c1", "category": "garbage", "ward": "w", "closed_by_hash": "s", "res_hours": 10.0,
             "has_attended_image": True, "citizen_image_only": False, "escalated": False, "complaint_type": "x", "zone": "z",
             "channel": "c", "location_precision": "exact"}]
    for i, h in enumerate(created_hours_after_close):
        rows.append({**rows[0], "ticket_id": f"r{i}", "created_at": (base + pd.Timedelta(hours=10 + h)).isoformat(),
                     "closed_at": None, "status": "open", "res_hours": None})
    # a far-future ticket so the label window of "orig" is fully observable
    rows.append({**rows[0], "ticket_id": "end", "h3": "other", "created_at": (base + pd.Timedelta(days=60)).isoformat(),
                 "closed_at": None, "status": "open", "res_hours": None})
    return fm.build(pd.DataFrame(rows)).set_index("ticket_id")


@pytest.mark.parametrize("hours,label", [([12], 0), ([30], 1), ([14 * 24 - 1], 1), ([15 * 24], 0), ([], 0), ([12, 40], 1)])
def test_mumbai_repeat_label_window(hours, label):
    df = _mumbai(hours)
    assert df.loc["orig", "y"] == label and bool(df.loc["orig", "label_observable"])


def test_mumbai_label_not_observable_near_end_of_data():
    df = _mumbai([])
    df2 = df.copy()
    assert not bool(df2.loc["end", "label_observable"])   # open ticket, never closed


# ---- model machinery ----
def _toy(n=3000, seed=1):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    cat = rng.choice(["a", "b", "c"], n)
    y = (rng.random(n) < 1 / (1 + np.exp(-(2 * x + (cat == "a")) + 1))).astype(int)
    return pd.DataFrame({"cat": cat, "x": x, "n2": rng.normal(size=n)}), y


def test_fit_predict_explain_and_selection_rule():
    X, y = _toy()
    tr, va, te = slice(0, 1800), slice(1800, 2400), slice(2400, 3000)
    cats = {"cat": ["a", "b", "c", "other"]}
    b = core.fit_ensemble("toy", "toy label", X[tr], y[tr], X[va], y[va], ["cat"], ["x", "n2"], cats, calibrate=True)
    assert b.ship in {"lgbm", "logistic", "ensemble"}
    # rule: the shipped model has the best VALIDATION auroc
    val = eval(b.notes[0].split("validation AUROC: ")[1])
    assert val[b.ship] == max(val.values())
    parts = core.predict_parts(b, X[te])
    assert set(parts) == {"lgbm", "logistic", "ensemble_raw", "ship"} and all(len(v) == 600 for v in parts.values())
    assert core.evaluate(y[te], parts["ship"], y[tr].mean())["auroc"] > 0.7
    ex = core.explain(b, X[te].iloc[:2], top=2)
    assert len(ex) == 2 and len(ex[0]) == 2 and {"feature", "value", "shap"} <= set(ex[0][0])


def test_uncalibrated_bundle_returns_rank_scores():
    X, y = _toy()
    b = core.fit_ensemble("toy", "t", X[:1800], y[:1800], X[1800:2400], y[1800:2400], ["cat"], ["x", "n2"], {"cat": ["a", "b", "c", "other"]}, calibrate=False)
    assert b.iso is None
    p = core.predict_parts(b, X[2400:])
    chosen = {"lgbm": p["lgbm"], "logistic": p["logistic"], "ensemble": p["ensemble_raw"]}[b.ship]
    assert np.allclose(p["ship"], chosen)


def test_unknown_categories_map_to_other_and_do_not_crash():
    X, y = _toy()
    b = core.fit_ensemble("toy", "t", X[:1800], y[:1800], X[1800:2400], y[1800:2400], ["cat"], ["x", "n2"], {"cat": ["a", "b", "c", "other"]})
    new = X[2400:2410].assign(cat="never-seen")
    assert len(core.predict_parts(b, new)["ship"]) == 10


def test_lift_tie_break_does_not_inherit_row_order():
    y = np.array([1] * 50 + [0] * 950)           # all positives first in time order
    constant = np.full(1000, 0.1)
    assert core.lift_at(y, constant, 0.10)["lift"] < 2.0   # a constant score must not look useful


# ---- synthetic features never read ground truth as a feature ----
def test_synthetic_features_exclude_ground_truth():
    assert not [c for c in fs.CAT_COLS + fs.NUM_COLS if c.startswith("gt_")]


# ---- score row -> contract ----
def _ticket(**kw):
    base = dict(ticket_id="t", city="mumbai", data_quality="real", source="s", category="drain", text="Removal of silt from nullah / culverts / rivers etc.", lang="other",
                lat=19.0, lng=72.8, h3="h", location_precision="exact", ward="w", created_at="2026-01-01T00:00:00Z",
                status="closed")
    base.update(kw)
    return Ticket(**base)


def test_from_row_unscored_is_baseline():
    s = from_row(_ticket(), {"_p": None})
    assert s.score_type == "baseline" and s.p_false_closure == 0.5 and s.model_version == "baseline-no-model"


def test_from_row_scored_carries_type_flags_and_eligibility():
    row = {"_p": 0.678, "_score_type": "rule_flags", "_pct": float("nan"), "_mv": "mum-flags-v1", "_flags": "citizen_image_only"}
    s = from_row(_ticket(), row)
    assert s.score_type == "rule_flags" and s.flags == ["citizen_image_only"] and s.risk_percentile is None
    assert s.satellite_eligible is True and "satellite" in s.eligible_checks
    # a ward-level Bengaluru ticket is never satellite-eligible even with a score
    s2 = from_row(_ticket(city="bengaluru", location_precision="ward_centroid"), {**row, "_score_type": "risk_rank_prior", "_pct": 0.9})
    assert s2.satellite_eligible is False and s2.risk_percentile == 0.9
    # a small problem is "not applicable" even with an exact point, and the score says why
    s3 = from_row(_ticket(category="garbage", text="Garbage / silt / tree branches not lifted"), row)
    assert s3.satellite_eligible is False and "satellite" not in s3.eligible_checks and s3.satellite_reason.startswith("not applicable")
    assert s.satellite_reason.startswith("eligible")
