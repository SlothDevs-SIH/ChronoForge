"""Mumbai features and label.

LABEL (proxy): a REPEAT complaint of the same category in the same ~100 m cell, created between 24 hours and 14 days
AFTER this ticket's closure. The 24 h gap drops same-day duplicates of the original problem.
It is only a proxy: a repeat can be a new problem, or one more neighbour reporting the same still-broken thing.
Earlier analysis (data/README.md): the plain 14-day version is 40% after closure against 49% in the 14 days BEFORE
filing, so the label is dominated by how crowded a spot is. That is why models here are compared against a
density-only model: only the lift over density counts as signal.

Tickets closed within 14 days of the end of the data are excluded (their window is not fully observed).
Features use only information at or before closure: the ticket itself, how it was closed, and earlier tickets nearby.
"""
import numpy as np
import pandas as pd

from .core import epoch_seconds

HOUR, DAY = 3600, 86400
CAT_COLS = ["category", "complaint_type", "zone", "channel"]
DENSITY_COLS = ["cell_cat_14d", "cell_cat_90d", "cell_all_14d", "ward_cat_30d"]
CLOSURE_COLS = ["log_res_hours", "fast_close", "has_attended_image", "citizen_image_only", "escalated", "staff_cnt_30d"]
TIME_COLS = ["hour", "dow"]
NUM_COLS = TIME_COLS + DENSITY_COLS + CLOSURE_COLS


def _groups(keys: list[pd.Series]):
    return pd.DataFrame({i: k.values for i, k in enumerate(keys)}).groupby(list(range(len(keys))), dropna=True).indices.values()


def _prior_counts(ts: np.ndarray, keys: list[pd.Series], days: int) -> np.ndarray:
    """Earlier rows (by created time) sharing the key within the previous `days` days. ts sorted ascending."""
    out = np.zeros(len(ts))
    for idx in _groups(keys):
        t = ts[idx]
        out[idx] = np.arange(len(t)) - np.searchsorted(t, t - days * DAY, side="left")
    return out


def build(tickets: pd.DataFrame) -> pd.DataFrame:
    df = tickets.copy()
    df["created_dt"] = pd.to_datetime(df["created_at"], utc=True)
    df["closed_dt"] = pd.to_datetime(df["closed_at"], utc=True)
    df["ts"] = epoch_seconds(df["created_dt"])
    df = df.sort_values(["ts", "ticket_id"], kind="stable").reset_index(drop=True)
    ts = df["ts"].to_numpy()
    local = df["created_dt"] + pd.Timedelta(hours=5, minutes=30)
    df["hour"], df["dow"] = local.dt.hour, local.dt.dayofweek

    df["cell_cat_14d"] = _prior_counts(ts, [df["h3"], df["category"]], 14)
    df["cell_cat_90d"] = _prior_counts(ts, [df["h3"], df["category"]], 90)
    df["cell_all_14d"] = _prior_counts(ts, [df["h3"]], 14)
    df["ward_cat_30d"] = _prior_counts(ts, [df["ward"], df["category"]], 30)
    df["staff_cnt_30d"] = _prior_counts(ts, [df["closed_by_hash"]], 30)

    df["log_res_hours"] = np.log1p(df["res_hours"].astype(float))
    df["fast_close"] = (df["res_hours"].astype(float) < 10 / 60).astype(float)
    for c in ("has_attended_image", "citizen_image_only", "escalated"):
        df[c] = df[c].map({True: 1.0, False: 0.0}).astype(float)
    for c in CAT_COLS:
        df[c] = df[c].fillna("unknown").astype(str)

    # label: repeat in the same cell and category created in (closed + 24h, closed + 14d]
    df["closed_ts"] = np.where(df["closed_dt"].notna(), epoch_seconds(df["closed_dt"].fillna(df["created_dt"])), -1)
    y = np.zeros(len(df), dtype=int)
    for idx in _groups([df["h3"], df["category"]]):
        t = ts[idx]                       # created times of every ticket in this cell+category, ascending
        c = df["closed_ts"].to_numpy()[idx]
        lo = np.searchsorted(t, c + HOUR * 24, side="right")
        hi = np.searchsorted(t, c + 14 * DAY, side="right")
        y[idx] = ((hi - lo) > 0) & (c > 0)
    df["y"] = y
    end = ts.max()
    df["label_observable"] = (df["closed_ts"] > 0) & (df["closed_ts"] <= end - 14 * DAY)
    return df
