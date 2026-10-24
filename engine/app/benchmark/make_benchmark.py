"""Injected-failure benchmark v1.

BASE: 1,000 real closed Mumbai tickets (exact location, valid, with a closing time and a closing officer).
INJECTED (invented by us): 30% are marked as false closures ("no real work was done"). Each failure may also show symptoms:
  fast_close      closed 1 to 9 minutes after filing
  photo_reuse     the closure photo id is copied from an earlier-closed ticket
  wrong_location  the closure photo's GPS is 300 to 5,000 m away (25% of the time only 120 to 300 m, which is ambiguous)
A "batch closing" symptom was DROPPED: in the real Mumbai data 28.9% of closed tickets share a closing minute with 2 or more
others closed by the same officer, often kilometres apart (bulk or desk closing), so it is normal here and carries no signal.
Not every failure has a symptom: failures with none can only be caught by independent evidence (satellite, citizen, human).
Clean tickets keep their real times; their photo ids are unique and their photo GPS error is small (1% GPS jumps of 150 to 600 m).

OUTPUTS: data/benchmark/benchmark_v1.parquet (tickets, no labels), benchmark_v1_truth.parquet (labels; benchmark use only)
         data/models/benchmark_v1.metrics.json (what the Engine-side checks catch, plus natural flag rates on ALL real tickets)
Everything here is SYNTHETIC INJECTION on real base tickets. Recall on injected symptoms is high by construction: the
informative numbers are the share of failures with NO symptom and the natural flag rates on real, un-injected tickets.

Usage (from engine/):  python -m app.benchmark.make_benchmark
"""
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[3]
SEED, N, FAIL_RATE = 7, 1000, 0.30
P = {"fast_close": 0.40, "photo_reuse": 0.35, "wrong_location": 0.30}
FAST_MIN, EXIF_MIN_M, PHOTO_SEEN = 10 / 60, 300.0, 1   # the Engine-side detector thresholds
COLS = ["ticket_id", "category", "ward", "lat", "lng", "h3", "created_at", "closed_at", "closed_by_hash", "res_hours",
        "closure_photo_id", "closure_photo_exif_dist_m"]


def _iso(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ")


def wilson(k: int, n: int) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    lo, hi = stats.beta.ppf(0.025, k, n - k + 1) if k else 0.0, stats.beta.ppf(0.975, k + 1, n - k) if k < n else 1.0
    return [round(float(lo), 4), round(float(hi), 4)]


def load_real() -> pd.DataFrame:
    df = pd.read_parquet(ROOT / "data/warehouse/tickets_mumbai.parquet")
    df = df[df["status"].isin(["closed", "reopened"]) & (df["location_precision"] == "exact") & df["closed_at"].notna()
            & df["closed_by_hash"].notna() & df["res_hours"].notna()].copy()
    df["created_dt"] = pd.to_datetime(df["created_at"], utc=True)
    df["closed_dt"] = pd.to_datetime(df["closed_at"], utc=True)
    return df


def build(real: pd.DataFrame, seed: int = SEED, n: int = N) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    base = real.sample(n=n, random_state=seed).sort_values("closed_dt").reset_index(drop=True)
    failures = set(rng.choice(n, size=int(n * FAIL_RATE), replace=False))

    closed = base["closed_dt"].copy()
    exif = np.abs(rng.normal(0, 40, n))
    jump = rng.random(n) < 0.01
    exif[jump] = rng.uniform(150, 600, jump.sum())
    photo = np.array([f"bm-{i:04d}" for i in range(n)], dtype=object)   # unique unless reused
    truth, reuse = [], []
    for i in range(n):
        modes = []
        if i in failures:
            modes.append("no_work")
            created = base.loc[i, "created_dt"]
            if rng.random() < P["fast_close"]:
                closed[i] = created + timedelta(minutes=float(rng.uniform(1, 9)))
                modes.append("fast_close")
            if rng.random() < P["photo_reuse"]:
                reuse.append(i)                                  # assigned below, once every closing time is final
                modes.append("photo_reuse")
            if rng.random() < P["wrong_location"]:
                exif[i] = rng.uniform(120, 300) if rng.random() < 0.25 else rng.uniform(300, 5000)
                modes.append("wrong_location")
        truth.append({"ticket_id": base.loc[i, "ticket_id"], "is_failure": int(i in failures), "modes": "+".join(modes) if modes else "none",
                      "site_changed": 0 if i in failures else 1})
    # photo reuse: copy the id of a ticket whose FINAL closing time is strictly earlier (so the reuse is on the later closure).
    # Done after the closing times are final, in time order, so a source's own photo id is already settled.
    for i in sorted(reuse, key=lambda j: closed[j]):
        earlier = np.flatnonzero((closed < closed[i]).to_numpy())
        if len(earlier):
            photo[i] = photo[earlier[rng.integers(len(earlier))]]
        else:                                                   # nothing earlier exists: drop the symptom, keep the failure
            truth[i]["modes"] = truth[i]["modes"].replace("+photo_reuse", "")
    out = base.copy()
    out["closed_dt"] = closed
    out["closed_at"] = [_iso(x) for x in closed]
    out["res_hours"] = ((closed - base["created_dt"]).dt.total_seconds() / 3600).round(3)
    out["closure_photo_id"], out["closure_photo_exif_dist_m"] = photo, np.round(exif, 1)
    return out[COLS].reset_index(drop=True), pd.DataFrame(truth)


# ---------------- Engine-side metadata detectors ----------------
def flags(df: pd.DataFrame) -> pd.DataFrame:
    """Which of four metadata checks fire on each ticket. Uses only the benchmark's own columns."""
    d = df.copy()
    d["closed_dt"] = pd.to_datetime(d["closed_at"], utc=True)
    order = d.sort_values("closed_dt").groupby("closure_photo_id").cumcount().reindex(d.index)   # 0 for the first holder
    return pd.DataFrame({"fast_close": d["res_hours"] < FAST_MIN, "photo_reuse": order >= PHOTO_SEEN,
                         "wrong_location": d["closure_photo_exif_dist_m"] > EXIF_MIN_M}, index=d.index)


def natural_rates(real: pd.DataFrame) -> dict:
    """Natural behaviour of the time-based signals on ALL real, un-injected Mumbai closed tickets."""
    f = flags(real.assign(closure_photo_id="x", closure_photo_exif_dist_m=0.0))
    n, k = len(real), int(f["fast_close"].sum())
    d = real.assign(_m=real["closed_dt"].dt.floor("min"))
    g = d.groupby(["closed_by_hash", "_m"]).agg(n=("ticket_id", "size"), dy=("lat", lambda x: (x.max() - x.min()) * 111320),
                                                  dx=("lng", lambda x: (x.max() - x.min()) * 111320 * np.cos(np.radians(19.1)))).reset_index()
    g["spread_m"] = np.hypot(g["dx"], g["dy"])
    multi = g[g["n"] >= 3]
    wide = lambda km: multi[multi["spread_m"] >= km * 1000]
    return {
        "n_real_closed_tickets": n,
        "fast_close_under_10_min": {"count": k, "rate": round(k / n, 5), "ci95": wilson(k, n),
                                    "reading": "rare, so a closure within 10 minutes of filing is a usable (weak) symptom"},
        "same_officer_same_minute_clusters": {
            "tickets_in_clusters_of_3_plus": int(multi["n"].sum()), "share_of_real_tickets": round(float(multi["n"].sum() / n), 4),
            "median_cluster_spread_m": round(float(multi["spread_m"].median()), 0),
            "share_in_clusters_spanning_1km_or_more": round(float(wide(1)["n"].sum() / n), 4),
            "share_in_clusters_spanning_3km_or_more": round(float(wide(3)["n"].sum() / n), 4),
            "reading": "NORMAL in this data, even across kilometres (bulk or desk closing): batch closing carries no signal and is NOT used."},
        "note": "photo_reuse and wrong_location cannot be measured on real data: it has no photos or photo GPS.",
    }


def evaluate(bench: pd.DataFrame, truth: pd.DataFrame, real: pd.DataFrame) -> dict:
    f, t = flags(bench), truth.set_index("ticket_id").loc[bench["ticket_id"]].reset_index(drop=True)
    fail, clean = t["is_failure"] == 1, t["is_failure"] == 0
    per_mode = {}
    for m in P:
        has = t["modes"].str.contains(m)
        k, nn = int((f[m] & has).sum()), int(has.sum())
        fp = int((f[m] & clean).sum())
        per_mode[m] = {"injected": nn, "caught": k, "recall": round(k / max(nn, 1), 3), "recall_ci95": wilson(k, nn),
                       "false_alarms_on_clean": fp, "false_alarm_rate_on_clean": round(fp / max(int(clean.sum()), 1), 4),
                       "false_alarm_ci95": wilson(fp, int(clean.sum())),
                       "precision_vs_all_clean_and_failures": round(float((f[m] & has).sum() / max(int(f[m].sum()), 1)), 3)}
    any_flag = f.any(axis=1)
    symptomatic = t["modes"].ne("no_work") & fail
    return {
        "n": int(len(bench)), "failures": int(fail.sum()), "clean": int(clean.sum()),
        "per_symptom": per_mode,
        "any_symptom_check": {"failures_flagged": int((any_flag & fail).sum()), "recall": round(float((any_flag & fail).sum() / max(fail.sum(), 1)), 3),
                              "clean_flagged": int((any_flag & clean).sum()), "false_alarm_rate_on_clean": round(float(any_flag[clean].mean()), 4)},
        "failures_with_no_symptom": {"count": int((fail & t["modes"].eq("no_work")).sum()), "share_of_failures": round(float((fail & t["modes"].eq("no_work")).sum() / max(fail.sum(), 1)), 3),
                                     "meaning": "closed with no observable metadata symptom: only independent evidence (satellite, photo content, citizen, human) can catch these"},
        "symptomatic_failures": int(symptomatic.sum()),
        "natural_flag_rates_real_data": natural_rates(real),
    }


def main() -> dict:
    real = load_real()
    bench, truth = build(real)
    out = ROOT / "data" / "benchmark"
    out.mkdir(parents=True, exist_ok=True)
    bench.to_parquet(out / "benchmark_v1.parquet", index=False)
    truth.to_parquet(out / "benchmark_v1_truth.parquet", index=False)
    metrics = {
        "name": "benchmark_v1", "WARNING": "SYNTHETIC INJECTION on real base tickets. Injected symptoms are caught by construction; "
                                          "read the share of failures with no symptom and the natural flag rates instead.",
        "base": "1,000 real closed Mumbai tickets (exact location), seed 7", "failure_rate_injected": FAIL_RATE,
        "injection_probabilities": P, "detector_thresholds": {"fast_close_minutes": 10, "wrong_location_m": EXIF_MIN_M, "photo_reuse": "seen on an earlier closure"},
        "dropped_symptom": "batch_close: normal in real Mumbai data (see natural_flag_rates_real_data), so it is neither injected nor detected",
        "results": evaluate(bench, truth, real),
        "pending": "Agent cost-versus-accuracy ('run everything' vs the budgeted agent) needs Ayush's real verifiers; photo content checks need the demo photo set.",
    }
    (ROOT / "data" / "models" / "benchmark_v1.metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
