"""Benchmark tests on a small fake 'real' frame (the real file is not needed)."""
import numpy as np
import pandas as pd
import pytest

from app.benchmark import make_benchmark as mb


@pytest.fixture(scope="module")
def real():
    rng = np.random.default_rng(0)
    n = 400
    created = pd.Timestamp("2026-04-01", tz="UTC") + pd.to_timedelta(rng.uniform(0, 120 * 24, n), unit="h")
    closed = created + pd.to_timedelta(rng.uniform(1, 400, n), unit="h")      # all well over 10 minutes
    return pd.DataFrame({
        "ticket_id": [f"mum-{i}" for i in range(n)], "category": "garbage", "ward": "w", "lat": 19.0 + rng.normal(0, 0.05, n),
        "lng": 72.85 + rng.normal(0, 0.05, n), "h3": "c", "created_dt": created, "closed_dt": closed,
        "created_at": [mb._iso(x) for x in created], "closed_at": [mb._iso(x) for x in closed],
        "closed_by_hash": rng.choice([f"o{i}" for i in range(15)], n), "res_hours": ((closed - created).total_seconds() / 3600).round(3)})


@pytest.fixture(scope="module")
def built(real):
    return mb.build(real, seed=7, n=300)


def test_deterministic_for_a_seed(real):
    a, ta = mb.build(real, seed=7, n=300)
    b, tb = mb.build(real, seed=7, n=300)
    assert a.equals(b) and ta.equals(tb)
    assert not mb.build(real, seed=8, n=300)[1].equals(ta)


def test_labels_are_not_in_the_ticket_table(built):
    bench, truth = built
    assert not {"is_failure", "modes", "site_changed"} & set(bench.columns)
    assert list(truth["ticket_id"]) == list(bench["ticket_id"]) and set(truth.columns) == {"ticket_id", "is_failure", "modes", "site_changed"}


def test_failure_rate_and_basic_structure(built):
    _, truth = built
    assert truth["is_failure"].sum() == 90                                   # 30% of 300
    fails, clean = truth[truth.is_failure == 1], truth[truth.is_failure == 0]
    assert fails["modes"].str.contains("no_work").all() and (fails["site_changed"] == 0).all()
    assert (clean["modes"] == "none").all() and (clean["site_changed"] == 1).all()


def test_batch_close_is_not_a_symptom_anywhere(built):
    _, truth = built
    assert not truth["modes"].str.contains("batch").any() and "batch_close" not in mb.P


def test_fast_close_injection_is_under_ten_minutes_and_detected(built):
    bench, truth = built
    fast = truth["modes"].str.contains("fast_close").to_numpy()
    assert fast.any() and (bench.loc[fast, "res_hours"] < 10 / 60).all()
    assert mb.flags(bench).loc[fast, "fast_close"].all()


def test_photo_reuse_always_points_at_an_earlier_closure_so_clean_tickets_are_not_flagged(built):
    bench, truth = built
    f = mb.flags(bench)
    reuse = truth["modes"].str.contains("photo_reuse").to_numpy()
    assert reuse.any() and f.loc[reuse, "photo_reuse"].all()
    clean = (truth["is_failure"] == 0).to_numpy()
    assert not f.loc[clean, "photo_reuse"].any()                              # the source is never the flagged one
    ids = bench.assign(c=pd.to_datetime(bench["closed_at"], utc=True))
    for i in np.flatnonzero(reuse):
        holders = ids[ids["closure_photo_id"] == bench.loc[i, "closure_photo_id"]]["c"]
        assert holders.min() < ids.loc[i, "c"]                                # another, earlier closure holds the same photo


def test_wrong_location_only_flags_above_the_threshold(built):
    bench, truth = built
    f = mb.flags(bench)
    assert (f["wrong_location"] == (bench["closure_photo_exif_dist_m"] > mb.EXIF_MIN_M)).all()
    wl = truth["modes"].str.contains("wrong_location").to_numpy()
    assert (bench.loc[wl, "closure_photo_exif_dist_m"] >= 120).all()
    assert f.loc[wl, "wrong_location"].mean() < 1.0                           # the ambiguous 120 to 300 m cases are missed on purpose


def test_evaluate_reports_symptomless_failures_and_stays_honest(built, real):
    bench, truth = built
    r = mb.evaluate(bench, truth, real)
    assert set(r["per_symptom"]) == {"fast_close", "photo_reuse", "wrong_location"}
    assert r["failures_with_no_symptom"]["count"] > 0 and r["any_symptom_check"]["recall"] < 1.0
    assert r["per_symptom"]["fast_close"]["recall"] == 1.0
    assert 0 <= r["any_symptom_check"]["false_alarm_rate_on_clean"] < 0.1


def test_natural_rates_expose_that_same_minute_clusters_are_normal():
    # 6 tickets, one officer, all closed in the same minute across ~3 km: a cluster that is spatially spread but routine
    t = pd.Timestamp("2026-05-01T10:00:30Z")
    real = pd.DataFrame({"ticket_id": [f"t{i}" for i in range(6)], "closed_dt": [t] * 6, "closed_by_hash": "o1",
                         "lat": [19.0 + 0.005 * i for i in range(6)], "lng": 72.85, "res_hours": 5.0, "closed_at": mb._iso(t)})
    r = mb.natural_rates(real)["same_officer_same_minute_clusters"]
    assert r["tickets_in_clusters_of_3_plus"] == 6 and r["share_in_clusters_spanning_1km_or_more"] == 1.0
    assert "NOT used" in r["reading"]


def test_wilson_interval_contains_the_estimate():
    lo, hi = mb.wilson(3, 100)
    assert lo < 0.03 < hi and mb.wilson(0, 50)[0] == 0.0 and mb.wilson(50, 50)[1] == 1.0
