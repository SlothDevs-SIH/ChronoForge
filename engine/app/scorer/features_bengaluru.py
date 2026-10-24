"""Bengaluru features and label.

LABEL: status == "reopened" (the citizen reopened the closure). It is a real but lower-bound signal: it needs a
citizen who persists and a department with a reopen workflow, so it measures "closure not accepted", not "false closure".

THREE TRAPS found in the data (see data/README.md and engine/app/scorer/README notes in metrics.json):
1. LEAKAGE, remarks: on reopened tickets the staff remark is overwritten ("citizen not satisfied", "not resolved").
2. LEAKAGE, staff: a reopened ticket is re-assigned to a senior officer, so "Staff Name"/role on a reopened ticket is the
   POST-reopen handler (May 2025: 354 of 438 reopened tickets show AEE, while closed ones show AE/JE/JHI/Marshal).
   A staff_role x category lookup alone scored AUROC 0.965 for exactly this reason. NO staff-derived feature is used.
3. The reopen mechanism only appears around 2024 (rate 0.02% in 2020, 1.5% in 2025), so earlier tickets are structural
   zeros, not negatives. Training uses only tickets created on or after CAPABLE_FROM.

What remains is information known before closure: category, sub-category, ward, zone, time of day, ward workload and
ward/sub-category history. Outcome-based rates (ward, sub-category) are LAGGED by 30 days because a reopen can arrive
weeks after closure.
"""
import numpy as np
import pandas as pd

from .core import epoch_seconds, top_categories

CAPABLE_FROM = pd.Timestamp("2024-10-01", tz="UTC")
LAG_DAYS = 30
DAY = 86400
CAT_COLS = ["category", "sub", "ward_zone"]
NUM_COLS = ["hour", "dow", "ward_cnt_30d", "ward_sub_14d", "ward_sub_90d", "ward_rate_lag30", "sub_rate_lag30"]


def _groups(keys: list[pd.Series]):
    return pd.DataFrame({i: k.values for i, k in enumerate(keys)}).groupby(list(range(len(keys))), dropna=True).indices.values()


def _prior_counts(ts: np.ndarray, keys: list[pd.Series], days: int) -> np.ndarray:
    """For each row: how many EARLIER rows share the key within the previous `days` days. ts must be sorted."""
    out = np.zeros(len(ts))
    for idx in _groups(keys):
        t = ts[idx]
        out[idx] = np.arange(len(t)) - np.searchsorted(t, t - days * DAY, side="left")
    return out


def _lagged_rate(ts, y, cap, keys: list[pd.Series], lag_days: int, base: float, alpha: float = 50.0) -> np.ndarray:
    """Smoothed label rate of the same key among capable-period rows that are at least `lag_days` older."""
    out = np.full(len(ts), base)
    yc, cc = (y * cap).astype(float), cap.astype(float)
    for idx in _groups(keys):
        t = ts[idx]
        hi = np.searchsorted(t, t - lag_days * DAY, side="right")
        csy, csc = np.concatenate([[0], np.cumsum(yc[idx])]), np.concatenate([[0], np.cumsum(cc[idx])])
        out[idx] = (csy[hi] + alpha * base) / (csc[hi] + alpha)
    return out


def build(tickets: pd.DataFrame, base_rate: float, sub_top: list[str] | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Returns (feature frame sorted by time, list of kept 'sub' categories)."""
    df = tickets.copy()
    dt = pd.to_datetime(df["created_at"], utc=True)
    df["created_dt"] = dt
    df["ts"] = epoch_seconds(dt)
    df = df.sort_values(["ts", "ticket_id"], kind="stable").reset_index(drop=True)
    local = df["created_dt"] + pd.Timedelta(hours=5, minutes=30)
    df["hour"], df["dow"] = local.dt.hour, local.dt.dayofweek
    df["sub"] = df["text"].fillna("other")
    if sub_top is None:
        sub_top = top_categories(df["sub"], 40)
    df["sub"] = df["sub"].where(df["sub"].isin(sub_top), "other")
    df["ward_zone"] = df["ward_zone"].fillna("unknown")
    ts = df["ts"].to_numpy()
    y = (df["status"] == "reopened").astype(int).to_numpy()
    cap = (df["created_dt"] >= CAPABLE_FROM).to_numpy()

    df["ward_cnt_30d"] = _prior_counts(ts, [df["ward"]], 30)
    df["ward_sub_14d"] = _prior_counts(ts, [df["ward"], df["sub"]], 14)
    df["ward_sub_90d"] = _prior_counts(ts, [df["ward"], df["sub"]], 90)
    df["ward_rate_lag30"] = _lagged_rate(ts, y, cap, [df["ward"]], LAG_DAYS, base_rate)
    df["sub_rate_lag30"] = _lagged_rate(ts, y, cap, [df["sub"]], LAG_DAYS, base_rate)
    df["y"] = y
    df["capable"] = cap
    return df, sub_top
