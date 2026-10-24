"""Synthetic-city features. LABEL is ground truth (gt_false_closure) from data/warehouse/truth_<city>.parquet.

Because the generator injects the failure modes, a high score here only shows that the model recovers what we injected.
Every number from this module must be labelled "synthetic injection". Ground truth is read only to build the label;
no gt_* column is ever a feature.
"""
import numpy as np
import pandas as pd

from .core import epoch_seconds

DAY = 86400
CAT_COLS = ["category", "lang"]
NUM_COLS = ["log_res_hours", "closed_hour", "note_blank", "note_len", "exif_dist_m", "photo_seen_before",
            "officer_minute_cnt", "cell_cat_14d", "ward_cat_30d", "officer_cnt_30d"]


def _groups(keys):
    return pd.DataFrame({i: k.values for i, k in enumerate(keys)}).groupby(list(range(len(keys))), dropna=True).indices.values()


def _prior_counts(ts, keys, days):
    out = np.zeros(len(ts))
    for idx in _groups(keys):
        t = ts[idx]
        out[idx] = np.arange(len(t)) - np.searchsorted(t, t - days * DAY, side="left")
    return out


def build(tickets: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    df = tickets.merge(truth[["ticket_id", "gt_false_closure"]], on="ticket_id", how="left")
    df["created_dt"] = pd.to_datetime(df["created_at"], utc=True)
    df["closed_dt"] = pd.to_datetime(df["closed_at"], utc=True)
    df["ts"] = epoch_seconds(df["created_dt"])
    df = df.sort_values(["ts", "ticket_id"], kind="stable").reset_index(drop=True)
    ts = df["ts"].to_numpy()
    df["log_res_hours"] = np.log1p(df["res_hours"].astype(float)) if "res_hours" in df else np.log1p((df["closed_dt"] - df["created_dt"]).dt.total_seconds() / 3600)
    df["closed_hour"] = df["closed_dt"].dt.hour.astype(float)
    note = df["closure_note"].fillna("")
    df["note_blank"] = ((note == "") | (note == ".")).astype(float)
    df["note_len"] = note.str.len().astype(float)
    df["exif_dist_m"] = df["closure_photo_exif_dist_m"].astype(float)
    # photo seen on an EARLIER closure (the first holder is clean, later ones are reuse)
    closed_ts = np.where(df["closed_dt"].notna(), epoch_seconds(df["closed_dt"].fillna(df["created_dt"])), -1)
    seen = np.zeros(len(df))
    for idx in _groups([df["closure_photo_id"]]):
        c = closed_ts[idx]
        order = np.argsort(c, kind="stable")
        rank = np.empty(len(idx)); rank[order] = np.arange(len(idx))
        seen[idx] = np.where(c > 0, rank, 0)
    df["photo_seen_before"] = seen
    minute = df["closed_dt"].dt.floor("min").astype(str)
    df["_min"] = minute.where(df["closed_dt"].notna())
    df["officer_minute_cnt"] = df.groupby(["closed_by_hash", "_min"])["ticket_id"].transform("size").sub(1).where(df["closed_dt"].notna(), 0).astype(float)
    df["cell_cat_14d"] = _prior_counts(ts, [df["h3"], df["category"]], 14)
    df["ward_cat_30d"] = _prior_counts(ts, [df["ward"], df["category"]], 30)
    df["officer_cnt_30d"] = _prior_counts(ts, [df["closed_by_hash"]], 30)
    df["y"] = df["gt_false_closure"].fillna(-1).astype(int)
    return df
