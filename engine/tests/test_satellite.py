"""Satellite verifier tests: synthetic arrays and fakes only, no network."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.satellite import change, scenes, verifier

H = W = 121
RNG = np.random.default_rng(3)


def _refl(base=(0.10, 0.12, 0.14, 0.30, 0.25)):
    """[5,H,W] reflectance with small pixel noise."""
    return np.stack([np.full((H, W), b) + RNG.normal(0, 0.004, (H, W)) for b in base]).astype(np.float32)


def _scl(invalid_box=None):
    scl = np.full((H, W), 5, dtype=np.uint8)
    if invalid_box:
        y0, y1, x0, x1 = invalid_box
        scl[y0:y1, x0:x1] = 9   # cloud
    return scl


def _site_slice(half=6):
    c = H // 2
    return slice(c - half, c + half + 1), slice(c - half, c + half + 1)


# ---------------- change.analyse ----------------
def test_scene_wide_shift_is_not_unusual_change_at_the_site():
    before = _refl()
    after = before + np.array([0.02, 0.02, 0.03, -0.04, 0.01], dtype=np.float32)[:, None, None]   # whole scene shifts (season)
    r = change.analyse(before, after, _scl(), _scl())
    assert "abstain" not in r and r["n_controls"] >= 20
    assert 0.05 < r["percentile"] < 0.95        # the site looks like its controls


def test_local_change_at_the_site_is_detected():
    before = _refl()
    after = before.copy()
    ys, xs = _site_slice(8)
    after[:, ys, xs] += np.array([0.05, 0.05, 0.06, -0.10, 0.08], dtype=np.float32)[:, None, None]
    r = change.analyse(before, after, _scl(), _scl())
    assert r["percentile"] >= 0.95 and r["z_score"] > 3


def test_controls_are_matched_on_the_pre_change_state():
    # left half is "water-like", right half "built-up". Change only the left half. The site is in the right half,
    # so it must be compared with right-half controls and the left-half change must not leak into its controls.
    before = _refl()
    before[:, :, : W // 2] = _refl((0.04, 0.06, 0.04, 0.02, 0.01))[:, :, : W // 2]
    after = before.copy()
    after[:, :, : W // 2] += np.array([0.05, 0.05, 0.05, 0.05, 0.05], dtype=np.float32)[:, None, None]
    r = change.analyse(before, after, _scl(), _scl(), min_dist=15)
    assert 0.05 < r["percentile"] < 0.95
    assert r["match_distance_median"] < 3


def test_cloudy_site_abstains():
    c = H // 2
    r = change.analyse(_refl(), _refl(), _scl(invalid_box=(c - 10, c + 10, c - 10, c + 10)), _scl())
    assert r["abstain"].startswith("the site is cloud-obscured") and r["site_valid"] < 0.7


def test_too_few_clear_controls_abstains():
    r = change.analyse(_refl(), _refl(), _scl(invalid_box=(0, H, 0, 40)), _scl(invalid_box=(0, H, 80, H)), min_controls=40)
    assert "abstain" in r and "comparison windows" in r["abstain"]


def test_detect_stats_null_and_injected_shift():
    ctrl = RNG.normal(0, [0.01, 0.01, 0.01, 0.005], size=(60, 4))
    null_pcts = [change.detect_stats(RNG.normal(0, [0.01, 0.01, 0.01, 0.005], size=4), ctrl)["percentile"] for _ in range(300)]
    assert 0.4 < np.mean(null_pcts) < 0.6 and 0.04 < np.mean(np.array(null_pcts) >= 0.9) < 0.18   # about 10% by construction
    big = change.detect_stats(np.array([0.06, -0.06, 0.06, 0.03]), ctrl)
    assert big["percentile"] > 0.98 and set(big["feature_z"]) == set(change.FEATURES)


def test_sigma_floor_prevents_division_blowup_on_constant_controls():
    ctrl = np.zeros((60, 4))
    r = change.detect_stats(np.array([0.002, 0.002, 0.002, 0.001]), ctrl)
    assert np.isfinite(r["z_score"]) and r["site_score"] < 1.0


# ---------------- scene selection ----------------
def _scene(sid, day, tile="T1", cloud=10.0):
    return scenes.Scene(id=sid, when=datetime(2026, 5, day, tzinfo=timezone.utc), tile=tile, cloud=cloud, baseline="05.12", hrefs={})


CREATED, CLOSED = datetime(2026, 5, 10, tzinfo=timezone.utc), datetime(2026, 5, 20, tzinfo=timezone.utc)


def _pair(monkeypatch, before, after, valid=lambda s: 1.0):
    monkeypatch.setattr(scenes, "search", lambda lat, lng, start, end, client=None: before if end <= CREATED else after)
    return scenes.choose_pair(0, 0, CREATED, CLOSED, client=object(), valid_fn=valid)


def test_pair_uses_latest_before_and_earliest_after_on_the_same_tile(monkeypatch):
    b, a, note = _pair(monkeypatch, [_scene("b1", 1), _scene("b2", 8)], [_scene("a1", 26), _scene("a2", 22)])
    assert (b.id, a.id, note) == ("b2", "a2", "")


def test_pair_skips_a_cloudy_closest_scene(monkeypatch):
    b, a, _ = _pair(monkeypatch, [_scene("b1", 1), _scene("b2", 8)], [_scene("a1", 22)], valid=lambda s: 0.1 if s.id == "b2" else 1.0)
    assert b.id == "b1"


def test_pair_notes_for_missing_or_unusable_scenes(monkeypatch):
    assert "before" in _pair(monkeypatch, [], [_scene("a", 22)])[2]
    assert "after" in _pair(monkeypatch, [_scene("b", 8)], [])[2]
    assert "different tiles" in _pair(monkeypatch, [_scene("b", 8, "T1")], [_scene("a", 22, "T2")])[2]
    assert "cloud-obscured" in _pair(monkeypatch, [_scene("b", 8)], [_scene("a", 22)], valid=lambda s: 0.0)[2]


def test_pair_prefers_the_tile_with_the_smaller_time_gap(monkeypatch):
    b, a, _ = _pair(monkeypatch, [_scene("bT1", 2, "T1"), _scene("bT2", 9, "T2")], [_scene("aT1", 29, "T1"), _scene("aT2", 21, "T2")])
    assert (b.id, a.id) == ("bT2", "aT2")


# ---------------- verifier ----------------
@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(verifier, "CACHE_DIR", tmp_path)
    return tmp_path


def _ticket(**kw):
    t = dict(ticket_id="mum-1", category="drain", text="Removal of silt from nullah / culverts / rivers etc.", lat=19.0, lng=72.8, created_at="2026-05-10T00:00:00Z",
             closed_at="2026-05-20T00:00:00Z", location_precision="exact", data_quality="real")
    t.update(kw)
    return t


def _analysis(pct):
    return {"percentile": pct, "z_score": 1.0, "site_valid": 1.0, "n_controls": 60, "match_distance_median": 0.5,
            "feature_z": {}, "site_delta": {}, "control_sigma": {}, "before": {"id": "b"}, "after": {"id": "a"},
            "days_before_filing": 2, "days_after_closing": 3, "seconds": 1.0}


@pytest.mark.parametrize("pct,verdict,lr", [(0.95, "supports_fix", verifier.LR_DETECT), (0.30, "contradicts_fix", verifier.LR_NO_DETECT)])
def test_verdict_and_lr_follow_the_percentile(cache, monkeypatch, pct, verdict, lr):
    monkeypatch.setattr(verifier, "measure", lambda *a, **k: _analysis(pct))
    ev = verifier.check_ticket(_ticket())
    assert (ev["verdict"], ev["likelihood_ratio"], ev["cost"]) == (verdict, lr, 3)
    assert ev["details"]["source"] == "live" and ev["details"]["percentile"] == pct


def test_lr_bounds_are_modest_by_design():
    assert 0.3 <= verifier.LR_DETECT < 1 < verifier.LR_NO_DETECT <= 1.5   # small works are invisible: never a strong claim


def test_second_call_is_served_from_the_cache(cache, monkeypatch):
    calls = []
    monkeypatch.setattr(verifier, "measure", lambda *a, **k: calls.append(1) or _analysis(0.95))
    verifier.check_ticket(_ticket())
    ev = verifier.check_ticket(_ticket())
    assert len(calls) == 1 and ev["details"]["source"] == "cached" and ev["verdict"] == "supports_fix"
    verifier.check_ticket(_ticket(), refresh=True)
    assert len(calls) == 2


def test_cached_only_never_measures(cache, monkeypatch):
    monkeypatch.setattr(verifier, "measure", lambda *a, **k: pytest.fail("must not read imagery"))
    ev = verifier.check_ticket(_ticket(), cached_only=True)
    assert ev["verdict"] == "inconclusive" and ev["cost"] == 0 and ev["details"]["source"] == "not_cached"


def test_abstention_is_inconclusive_with_the_reason_and_still_costs(cache, monkeypatch):
    monkeypatch.setattr(verifier, "measure", lambda *a, **k: {"abstain": "the site is cloud-obscured in every nearby before or after scene", "seconds": 5})
    ev = verifier.check_ticket(_ticket())
    assert ev["verdict"] == "inconclusive" and ev["likelihood_ratio"] == 1.0 and ev["cost"] == 3
    assert "cloud" in ev["details"]["reason"] and ev["details"]["abstained"] is True


def test_imagery_errors_abstain_instead_of_crashing(cache, monkeypatch):
    def boom(*a, **k):
        raise OSError("connection reset")
    monkeypatch.setattr(verifier, "measure", boom)
    ev = verifier.check_ticket(_ticket())
    assert ev["verdict"] == "inconclusive" and "imagery read failed" in ev["details"]["reason"]


def test_synthetic_tickets_never_carry_weight(cache, monkeypatch):
    monkeypatch.setattr(verifier, "measure", lambda *a, **k: _analysis(0.99))
    ev = verifier.check_ticket(_ticket(data_quality="synthetic"))
    assert ev["verdict"] == "inconclusive" and ev["likelihood_ratio"] == 1.0
    assert ev["details"]["demo_only"] is True and ev["details"]["measured_verdict"] == "supports_fix"


@pytest.mark.parametrize("kw,fragment", [
    (dict(category="pothole", text="Pothole on road"), "not applicable"),
    (dict(category="garbage", text="Garbage / silt / tree branches not lifted"), "not applicable"),
    (dict(category="drain", text="Raise / broken / missing manhole cover"), "not applicable"),
    (dict(text=None), "not applicable"),
    (dict(location_precision="ward_centroid"), "no exact location"),
    (dict(closed_at=None), "no closing date"),
])
def test_ineligible_tickets_are_free_and_explained(cache, monkeypatch, kw, fragment):
    monkeypatch.setattr(verifier, "measure", lambda *a, **k: pytest.fail("must not read imagery"))
    ev = verifier.check_ticket(_ticket(**kw))
    assert ev["cost"] == 0 and ev["verdict"] == "inconclusive" and fragment in ev["details"]["reason"]
    assert ev["details"]["eligible"] is False


def test_assumptions_are_stated_and_consistent():
    a = verifier.assumptions()
    assert a["LR_detect"] == round(a["P_detect_given_not_fixed"] / a["P_detect_given_fixed"], 2)
    assert verifier.LR_NO_DETECT <= a["LR_no_detect"]    # the shipped ratio is never more confident than the stated arithmetic


@pytest.mark.parametrize("text,large", [
    ("Removal of silt from nullah / culverts / rivers etc.", True),
    ("Removal of unauthorised structures on Nallas", True),
    ("Foul smell from drain  / pumping station / dumping ground", True),
    ("Illegal Dumping", True),
    ("Severe waterlogging on the main road for 300 m", True),
    ("Water logging near the underpass", True),
    ("Area flooded after rain", True),
    ("Pothole on road", False),
    ("Garbage / silt / tree branches not lifted", False),
    ("Removal of Debris", False),
    ("Encrochment on BMC Land / Footpath / drains", False),
    ("Unauthorised construction / shed", False),
    ("Drain / manholes  block or overflow", False),
    ("Garbage has not been cleared for several days.", False),
    ("", False),
    (None, False),
])
def test_only_large_area_wording_is_satellite_eligible(text, large):
    from app.eligibility import satellite_eligibility
    ok, why = satellite_eligibility("garbage", "exact", text)
    assert ok is large
    assert why.startswith("eligible") if large else why.startswith("not applicable")


def test_not_applicable_explains_the_large_area_scope():
    from app.eligibility import satellite_eligibility
    for cat, text in (("pothole", "Pothole"), ("garbage", "Garbage not lifted")):
        why = satellite_eligibility(cat, "exact", text)[1]
        assert "10 m" in why and "large-area" in why or "large area" in why


# ---------------- network robustness (the first validation run lost a quarter of its checks to read errors) ----------------
import rasterio.errors
from rasterio.transform import from_origin

from app.satellite import reader


class _FakeDS:
    transform = from_origin(0, 100, 10, 10)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, *a, **k):
        return np.ones((10, 10), dtype=np.uint16)


def test_read_band_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def flaky(href, attempts=4):
        calls["n"] += 1
        if calls["n"] < 3:
            raise rasterio.errors.RasterioIOError("Read failed")
        return _FakeDS()
    monkeypatch.setattr(reader, "_open", flaky)
    monkeypatch.setattr(reader.time, "sleep", lambda s: None)
    out = reader._read_band("x", (0, 0, 100, 100), (10, 10), reader.Resampling.nearest)
    assert calls["n"] == 3 and out.shape == (10, 10)


def test_read_band_gives_up_after_the_configured_attempts(monkeypatch):
    calls = {"n": 0}

    def dead(href, attempts=4):
        calls["n"] += 1
        raise rasterio.errors.RasterioIOError("Read failed")
    monkeypatch.setattr(reader, "_open", dead)
    monkeypatch.setattr(reader.time, "sleep", lambda s: None)
    with pytest.raises(rasterio.errors.RasterioIOError):
        reader._read_band("x", (0, 0, 100, 100), (10, 10), reader.Resampling.nearest)
    assert calls["n"] == reader.READ_ATTEMPTS


def test_a_retrying_read_does_not_hold_a_connection_slot(monkeypatch):
    # with 1 slot, a read that is sleeping between retries must have released it, or this would deadlock
    import threading
    monkeypatch.setattr(reader, "_CONNECTIONS", threading.BoundedSemaphore(1))
    held_during_sleep = []

    def flaky(href, attempts=4):
        if not held_during_sleep:
            raise rasterio.errors.RasterioIOError("Read failed")
        return _FakeDS()
    monkeypatch.setattr(reader, "_open", flaky)

    def sleep(s):
        got = reader._CONNECTIONS.acquire(blocking=False)
        held_during_sleep.append(got)
        if got:
            reader._CONNECTIONS.release()
    monkeypatch.setattr(reader.time, "sleep", sleep)
    reader._read_band("x", (0, 0, 100, 100), (10, 10), reader.Resampling.nearest)
    assert held_during_sleep == [True]


def test_window_level_retry_then_raise(monkeypatch):
    calls = {"n": 0}

    def bad(hrefs, baseline, bbox, workers=6):
        calls["n"] += 1
        raise rasterio.errors.RasterioIOError("Read failed")
    monkeypatch.setattr(reader, "read_window", bad)
    monkeypatch.setattr(verifier.time, "sleep", lambda s: None)
    with pytest.raises(rasterio.errors.RasterioIOError):
        verifier._read_with_retry(type("S", (), {"hrefs": {}, "baseline": "05.12"})(), (0, 0, 1, 1))
    assert calls["n"] == 2


def test_transient_failures_are_never_cached(cache, monkeypatch):
    def boom(*a, **k):
        raise rasterio.errors.RasterioIOError("Read failed")
    monkeypatch.setattr(verifier, "measure", boom)
    ev = verifier.check_ticket(_ticket())
    assert ev["verdict"] == "inconclusive" and "imagery read failed" in ev["details"]["reason"]
    assert not verifier.cache_path("mum-1").exists()          # a retry later must be able to succeed


def test_deterministic_abstentions_are_cached_but_failures_are_not(cache, monkeypatch):
    monkeypatch.setattr(verifier, "measure", lambda *a, **k: {"abstain": "the site is cloud-obscured in every nearby before or after scene"})
    verifier.check_ticket(_ticket())
    assert verifier.cache_path("mum-1").exists()              # clouds will still be there next time: caching saves a 40 s read
