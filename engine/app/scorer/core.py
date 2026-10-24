"""Shared model machinery: LightGBM + logistic ensemble, isotonic calibration, TreeSHAP reasons, honest metrics.

Every city gets its own features and label (see the features_*.py modules). Nothing here knows about a city.
Split is always by time: train on earlier rows, tune and calibrate on a middle slice, report on the latest slice.
"""
from dataclasses import dataclass, field
from typing import Any, Optional

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

SEED = 7


def epoch_seconds(dt: pd.Series) -> np.ndarray:
    """Seconds since epoch for a tz-aware datetime Series. Never use astype("int64") // 10**9: the datetime unit
    differs by pandas version (microseconds here) and that silently turned every "30-day" window into decades."""
    return ((dt - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)).astype("int64").to_numpy()


@dataclass
class Bundle:
    name: str
    label_definition: str
    cat_cols: list[str]
    num_cols: list[str]
    categories: dict[str, list]
    lgb: Any
    lr: Any
    w_lgb: float
    ship: str                        # which output is the score: lgbm | logistic | ensemble (chosen on VALIDATION auroc)
    iso: Any                         # None when the label is too unstable to calibrate (rank score only)
    base_rate: float                 # label rate in the training slice
    train_rows: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def feature_cols(self) -> list[str]:
        return self.cat_cols + self.num_cols


def top_categories(s: pd.Series, n: int, min_count: int = 200) -> list[str]:
    vc = s.value_counts()
    return [k for k, c in vc.head(n).items() if c >= min_count]


def to_frame(X: pd.DataFrame, cat_cols: list[str], num_cols: list[str], categories: dict[str, list]) -> pd.DataFrame:
    """Fixed category sets so train, validation, test and live scoring all encode identically."""
    out = X[cat_cols + num_cols].copy()
    for c in cat_cols:
        out[c] = pd.Categorical(out[c].where(out[c].isin(categories[c]), "other"), categories=categories[c])
    for c in num_cols:
        out[c] = pd.to_numeric(out[c], errors="coerce").astype(float)
    return out


def _lr_pipeline(cat_cols: list[str], num_cols: list[str]) -> Pipeline:
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=30), cat_cols),
        ("num", Pipeline([("scale", StandardScaler())]), num_cols),
    ])
    return Pipeline([("pre", pre), ("lr", LogisticRegression(C=0.3, max_iter=800))])


def _lr_frame(X: pd.DataFrame, cat_cols, num_cols) -> pd.DataFrame:
    out = X.copy()
    for c in cat_cols:
        out[c] = out[c].astype(str)
    for c in num_cols:
        out[c] = out[c].fillna(out[c].median() if out[c].notna().any() else 0.0)
    return out


def _lgb_params(n_pos: int) -> dict:
    return dict(objective="binary", n_estimators=600, learning_rate=0.04, num_leaves=31,
                min_child_samples=max(40, min(200, n_pos // 20 or 40)), subsample=0.8, subsample_freq=1,
                colsample_bytree=0.8, reg_lambda=5.0, random_state=SEED, verbose=-1, n_jobs=4)


def fit_ensemble(name: str, label_definition: str, Xtr, ytr, Xva, yva, cat_cols, num_cols,
                 categories: dict[str, list], calibrate: bool = True) -> Bundle:
    Xtr, Xva = to_frame(Xtr, cat_cols, num_cols, categories), to_frame(Xva, cat_cols, num_cols, categories)
    gbm = lgb.LGBMClassifier(**_lgb_params(int(ytr.sum())))
    gbm.fit(Xtr, ytr, eval_set=[(Xva, yva)], callbacks=[lgb.early_stopping(50, verbose=False)])
    lr = _lr_pipeline(cat_cols, num_cols)
    lr.fit(_lr_frame(Xtr, cat_cols, num_cols), ytr)

    p_g = gbm.predict_proba(Xva)[:, 1]
    p_l = lr.predict_proba(_lr_frame(Xva, cat_cols, num_cols))[:, 1]
    # blend weight chosen on the validation slice by log loss
    ws = np.linspace(0, 1, 11)
    w = float(ws[int(np.argmin([log_loss(yva, np.clip(x * p_g + (1 - x) * p_l, 1e-6, 1 - 1e-6)) for x in ws]))])
    blended = np.clip(w * p_g + (1 - w) * p_l, 1e-6, 1 - 1e-6)
    # pre-declared rule: ship whichever of the three has the best VALIDATION AUROC (never look at the test slice)
    val_auc = {"lgbm": roc_auc_score(yva, p_g), "logistic": roc_auc_score(yva, p_l), "ensemble": roc_auc_score(yva, blended)}
    ship = max(val_auc, key=val_auc.get)
    chosen = {"lgbm": p_g, "logistic": p_l, "ensemble": blended}[ship]
    iso = IsotonicRegression(out_of_bounds="clip", y_min=1e-5, y_max=1 - 1e-5).fit(chosen, yva) if calibrate else None
    return Bundle(name, label_definition, cat_cols, num_cols, categories, gbm, lr, w, ship, iso,
                  base_rate=float(ytr.mean()), train_rows=len(ytr), notes=[f"validation AUROC: { {k: round(v, 4) for k, v in val_auc.items()} }"])


def predict_parts(b: Bundle, X: pd.DataFrame) -> dict[str, np.ndarray]:
    Xf = to_frame(X, b.cat_cols, b.num_cols, b.categories)
    p_g = b.lgb.predict_proba(Xf)[:, 1]
    p_l = b.lr.predict_proba(_lr_frame(Xf, b.cat_cols, b.num_cols))[:, 1]
    blend = np.clip(b.w_lgb * p_g + (1 - b.w_lgb) * p_l, 1e-6, 1 - 1e-6)
    chosen = {"lgbm": p_g, "logistic": p_l, "ensemble": blend}[b.ship]
    return {"lgbm": p_g, "logistic": p_l, "ensemble_raw": blend,
            "ship": b.iso.predict(chosen) if b.iso is not None else chosen}


def explain(b: Bundle, X: pd.DataFrame, top: int = 3) -> list[list[dict]]:
    """TreeSHAP contributions from LightGBM (log-odds scale), top features per row."""
    Xf = to_frame(X, b.cat_cols, b.num_cols, b.categories)
    contrib = b.lgb.predict(Xf, pred_contrib=True)[:, :-1]
    out = []
    for i in range(len(Xf)):
        idx = np.argsort(-np.abs(contrib[i]))[:top]
        out.append([{"feature": b.feature_cols[j], "value": _scalar(X.iloc[i][b.feature_cols[j]]),
                     "shap": round(float(contrib[i][j]), 4)} for j in idx])
    return out


def _scalar(v):
    if isinstance(v, (np.floating, float)):
        return None if np.isnan(v) else round(float(v), 4)
    if isinstance(v, (np.integer, int)):
        return int(v)
    return str(v)


# ---------------- metrics ----------------
def lift_at(y: np.ndarray, p: np.ndarray, frac: float) -> dict:
    k = max(1, int(len(y) * frac))
    # random tie-break so constant scores do not inherit the row order (which is time order)
    top = np.lexsort((np.random.default_rng(SEED).random(len(p)), -p))[:k]
    hit = float(y[top].sum())
    return {"frac": frac, "n": k, "captured": hit, "precision": hit / k,
            "recall": hit / max(y.sum(), 1), "lift": (hit / k) / max(y.mean(), 1e-12)}


def bootstrap_auc(y, p, n=200, seed=SEED) -> list[float]:
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() == y[i].max():
            continue
        vals.append(roc_auc_score(y[i], p[i]))
    return [round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)]


def reliability(y, p, bins: int = 10) -> list[dict]:
    q = np.quantile(p, np.linspace(0, 1, bins + 1))
    out = []
    for lo, hi in zip(q[:-1], q[1:]):
        m = (p >= lo) & (p <= hi if hi == q[-1] else p < hi)
        if m.sum():
            out.append({"predicted": round(float(p[m].mean()), 5), "observed": round(float(y[m].mean()), 5), "n": int(m.sum())})
    return out


def evaluate(y: np.ndarray, p: np.ndarray, ref_rate: float) -> dict:
    y = np.asarray(y)
    brier = brier_score_loss(y, p)
    ref = brier_score_loss(y, np.full_like(p, ref_rate, dtype=float))
    return {"n": int(len(y)), "positives": int(y.sum()), "base_rate": round(float(y.mean()), 5),
            "auroc": round(float(roc_auc_score(y, p)), 4), "auroc_ci95": bootstrap_auc(y, p),
            "pr_auc": round(float(average_precision_score(y, p)), 5), "brier": round(float(brier), 6),
            "brier_skill_vs_train_rate": round(1 - brier / ref, 4),
            "lift_top1pct": lift_at(y, p, 0.01), "lift_top10pct": lift_at(y, p, 0.10)}


def eval_all(y, parts: dict[str, np.ndarray], baselines: dict[str, np.ndarray], ref_rate: float) -> dict:
    rows = {k: evaluate(y, v, ref_rate) for k, v in baselines.items()}
    rows.update({k: evaluate(y, v, ref_rate) for k, v in parts.items()})
    return rows
