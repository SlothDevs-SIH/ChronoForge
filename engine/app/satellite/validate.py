"""Validation of the satellite verifier. There are no real repair labels, so we measure two honest things:

1. PLACEBO: run the whole pipeline (scene choice, reads, controls) at random Mumbai locations and random date pairs where
   no repair is being claimed. A site should look "unusual" (percentile >= 0.90) about 10% of the time; the percentile
   should be roughly uniform. Also: abstention rate, runtime, and how often the sigma floor decides the scale.
2. POWER: add a known change of m control-sigmas to the site's index differences and measure how often it is detected.
   This is the sensitivity curve: the smallest change that is visible at 10 m resolution.

Usage (from engine/):  python -m app.satellite.validate --n 40
Writes data/models/satellite.metrics.json (committed) and data/cache/satellite_validation.json (raw runs, gitignored).
"""
import argparse
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
from scipy import stats

from . import change, verifier

ROOT = Path(__file__).resolve().parents[3]


def sample_runs(n: int, seed: int) -> list[dict]:
    """Placebo pairs: the DATES of one real closed ticket (so the season and cloud mix match real use) with the LOCATION
    of a different real ticket. No repair is claimed at that location."""
    con = duckdb.connect()
    tix = str(ROOT / "data/warehouse/tickets_mumbai.parquet")
    dates = con.execute("select created_at, closed_at from read_parquet(?) where status='closed' and location_precision='exact' "
                        "and category in ('garbage','drain') and closed_at < '2026-09-01'", [tix]).fetchall()
    locs = con.execute("select distinct on (h3) lat, lng, h3 from read_parquet(?) where location_precision='exact'", [tix]).fetchall()
    rng = random.Random(seed)
    rng.shuffle(dates); rng.shuffle(locs)
    parse = lambda x: datetime.fromisoformat(x.replace("Z", "+00:00"))
    return [{"lat": la, "lng": ln, "h3": cell, "created": parse(c), "closed": parse(cl)}
            for (la, ln, cell), (c, cl) in zip(locs[:n], dates[:n])]


def one(run: dict) -> dict:
    try:
        res = verifier.measure(run["lat"], run["lng"], run["created"], run["closed"])
    except Exception as exc:
        return {**{k: run[k] for k in ("lat", "lng", "h3")}, "abstain": f"error: {type(exc).__name__}: {str(exc)[:80]}"}
    out = {k: run[k] for k in ("lat", "lng", "h3")}
    out["seconds"] = res.get("seconds")
    if "abstain" in res:
        out["abstain"] = res["abstain"]
        return out
    ctrl = res["_controls"]
    raw_sig = 1.4826 * np.median(np.abs(ctrl - np.median(ctrl, 0)), 0)
    out.update(percentile=res["percentile"], z_score=res["z_score"], site=res["_site"].tolist(), controls=ctrl.tolist(),
               floor_bound=(raw_sig < change.SIGMA_FLOOR).tolist(), raw_sigma=raw_sig.tolist(),
               days_before=res["days_before_filing"], days_after=res["days_after_closing"])
    return out


def power_curve(done: list[dict], ms=(0, 0.5, 1, 1.5, 2, 3, 4, 6), pct: float = verifier.DETECT_PCT, seeds: int = 5) -> list[dict]:
    """Inject a change of m control-sigmas into every feature (random sign per feature and run) and count detections."""
    rng = np.random.default_rng(7)
    out = []
    for m in ms:
        hits = tot = 0
        for r in done:
            site, ctrl = np.array(r["site"]), np.array(r["controls"])
            sig = np.maximum(1.4826 * np.median(np.abs(ctrl - np.median(ctrl, 0)), 0), change.SIGMA_FLOOR)
            for _ in range(seeds):
                shifted = site + m * sig * rng.choice([-1.0, 1.0], size=4)
                hits += change.detect_stats(shifted, ctrl)["percentile"] >= pct
                tot += 1
        out.append({"injected_change_in_control_sigmas": m, "detection_rate": round(hits / tot, 3), "n": tot})
    return out


def run(n: int = 40, seed: int = 7, workers: int = 3) -> dict:
    t0 = time.time()
    runs = sample_runs(n, seed)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, runs))
    done = [r for r in results if "percentile" in r]
    abst = [r["abstain"] for r in results if "abstain" in r]
    pcts = np.array([r["percentile"] for r in done])
    ks = stats.kstest(pcts, "uniform") if len(pcts) >= 8 else None
    floor_share = float(np.mean([r["floor_bound"] for r in done], 0).mean()) if done else None
    typical_sigma = {f: round(float(np.median([r["raw_sigma"][i] for r in done])), 4) for i, f in enumerate(change.FEATURES)} if done else {}
    k = int((pcts >= verifier.DETECT_PCT).sum()) if len(pcts) else 0
    lo, hi = (stats.beta.ppf(0.025, k, len(pcts) - k + 1) if k else 0.0, stats.beta.ppf(0.975, k + 1, len(pcts) - k)) if len(pcts) else (None, None)
    metrics = {
        "what": "satellite verifier validation: placebo (no repair claimed) and injected-change sensitivity",
        "WARNING": "There are no real repair labels, so this does NOT show the verifier finds real repairs. It shows how it behaves "
                   "when nothing is claimed (placebo) and how large a change must be to be seen (power).",
        "n_requested": n, "n_measured": len(done), "n_abstained": len(abst),
        "abstention_rate": round(len(abst) / max(len(results), 1), 3),
        "abstention_reasons": {r: abst.count(r) for r in sorted(set(abst))},
        "outcome_split": {"requested": n, "measured": len(done), "cloud_obscured": sum("cloud" in r for r in abst),
                          "network_read_errors": sum(r.startswith("error:") for r in abst)},
        "seconds_total": round(time.time() - t0, 1),
        "seconds_per_check_median": round(float(np.median([r["seconds"] for r in results if r.get("seconds")])), 1) if any(r.get("seconds") for r in results) else None,
        "placebo": {
            "detect_threshold_percentile": verifier.DETECT_PCT, "expected_detection_rate": round(1 - verifier.DETECT_PCT, 2),
            "observed_detection_rate": round(k / len(pcts), 3) if len(pcts) else None,
            "observed_ci95": [round(float(lo), 3), round(float(hi), 3)] if len(pcts) else None,
            "mean_percentile": round(float(pcts.mean()), 3) if len(pcts) else None, "expected_mean_percentile": 0.5,
            "ks_vs_uniform_pvalue": round(float(ks.pvalue), 4) if ks else None,
            "sigma_floor_binding_share": round(floor_share, 3) if floor_share is not None else None,
            "typical_control_sigma_index_units": typical_sigma,
        },
        "power": power_curve(done) if done else [],
        "caveat": "Random locations can contain real unrelated change (construction, vegetation), so the placebo detection rate is an upper bound on the false-alarm rate for 'no repair'.",
    }
    (ROOT / "data" / "models").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "models" / "satellite.metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    cache = ROOT / "data" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "satellite_validation.json").write_text(json.dumps(results, default=str), encoding="utf-8")
    return metrics


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    print(json.dumps(run(a.n, a.seed, a.workers), indent=2))
