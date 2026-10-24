"""Train the scorers and write their outputs.

  bengaluru  trained model on the real reopen label            -> RANK score, mapped to a bounded prior
  mumbai     NO trained model: one rule flag with a measured effect (the repeat label is mostly density)
  pune       trained model on synthetic ground truth           -> calibrated probability (synthetic world only)
  synthetic  Sandbox City: scored by the Pune model (also the out-of-city test)

Outputs (models and warehouse files are gitignored; metrics JSON is committed):
  data/models/<name>.joblib, data/models/<name>.metrics.json
  data/warehouse/scores_<city>.parquet   unified columns: ticket_id, p_false_closure, score_type, risk_percentile,
                                         model_version, flags
  data/warehouse/features_<city>.parquet used at request time for per-ticket TreeSHAP reasons

Usage (from engine/):  python -m app.scorer.train bengaluru|mumbai|pune|all
"""
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from . import core
from . import features_bengaluru as fb
from . import features_mumbai as fm
from . import features_synthetic as fs

DATA = Path(__file__).resolve().parents[3] / "data"
MODELS = DATA / "models"
WAREHOUSE = DATA / "warehouse"
PRIOR_LOW, PRIOR_SPAN = 0.30, 0.40     # real-city priors live in [0.30, 0.70] so evidence, not the prior, decides
FLAG_PRIOR_CAP = 0.70
PRIOR_CLIP = (0.02, 0.98)              # synthetic calibrated priors are clipped to this range


def rank_prior(pct: np.ndarray) -> np.ndarray:
    return PRIOR_LOW + PRIOR_SPAN * np.asarray(pct, dtype=float)


def _write_scores(city: str, ids, prior, score_type: str, version: str, pct=None, flags=None) -> None:
    pd.DataFrame({"ticket_id": np.asarray(ids), "p_false_closure": np.asarray(prior, dtype=float), "score_type": score_type,
                  "risk_percentile": pct if pct is not None else np.nan, "model_version": version,
                  "flags": flags if flags is not None else ""}).to_parquet(WAREHOUSE / f"scores_{city}.parquet", index=False)


def _save(name: str, obj: dict, metrics: dict) -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    joblib.dump(obj, MODELS / f"{name}.joblib")
    (MODELS / f"{name}.metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")


def _rate_baseline(train: pd.DataFrame, test: pd.DataFrame, cols: list[str], base: float) -> np.ndarray:
    g = train.groupby(cols)["y"].agg(["sum", "count"])
    m = test[cols].merge(g, left_on=cols, right_index=True, how="left")
    return ((m["sum"].fillna(0) + 50 * base) / (m["count"].fillna(0) + 50)).to_numpy()


def _cats(tr: pd.DataFrame, cols: list[str]) -> dict[str, list]:
    return {c: list(dict.fromkeys(sorted(set(tr[c].astype(str))) + ["other"])) for c in cols}


def _results(bundle, y, parts, baselines, base) -> dict:
    shown = {k: v for k, v in parts.items() if k != "ship"} | {f"SHIPPED({bundle.ship})": parts["ship"]}
    return core.eval_all(y, shown, baselines, base)


# ---------------------------------------------------------------- Bengaluru
def train_bengaluru() -> dict:
    t0 = time.time()
    raw = pd.read_parquet(WAREHOUSE / "tickets_bengaluru.parquet")
    t_train, t_valid = pd.Timestamp("2025-03-01", tz="UTC"), pd.Timestamp("2025-05-01", tz="UTC")
    first, _ = fb.build(raw, base_rate=0.008)
    base = float(first[first["capable"] & first["status"].isin(["closed", "reopened"]) & (first["created_dt"] < t_train)]["y"].mean())
    df, sub_top = fb.build(raw, base_rate=base)   # outcome rates inside the features use the TRAINING-window base rate only

    closed = df[df["status"].isin(["closed", "reopened"]) & df["capable"]]
    tr, va, te = (closed[closed["created_dt"] < t_train], closed[(closed["created_dt"] >= t_train) & (closed["created_dt"] < t_valid)],
                  closed[closed["created_dt"] >= t_valid])
    bundle = core.fit_ensemble("blr-reopen-v1", "citizen reopened the closure (status ReOpen); tickets created Oct 2024 onward",
                               tr, tr["y"].to_numpy(), va, va["y"].to_numpy(), fb.CAT_COLS, fb.NUM_COLS, _cats(tr, fb.CAT_COLS), calibrate=False)
    parts, y = core.predict_parts(bundle, te), te["y"].to_numpy()
    baselines = {"baseline_constant_train_rate": np.full(len(te), base),
                 "baseline_category_rate": _rate_baseline(tr, te, ["category"], base),
                 "baseline_subcategory_rate": _rate_baseline(tr, te, ["sub"], base),
                 "baseline_ward_lagged_rate": te["ward_rate_lag30"].to_numpy()}
    metrics = {
        "model": bundle.name, "score_type": "risk_rank_prior", "data_quality": "real (proxy label)", "label": bundle.label_definition,
        "splits": {"train": f"created before 2025-03-01 ({len(tr)} rows, {int(tr['y'].sum())} reopened)",
                   "validation": f"2025-03-01 to 2025-04-30 ({len(va)} rows, {int(va['y'].sum())} reopened)",
                   "test": f"2025-05-01 onward ({len(te)} rows, {int(te['y'].sum())} reopened)"},
        "shipped_model": bundle.ship, "selection_rule": "best validation AUROC, fixed before looking at the test slice",
        "validation_auroc": bundle.notes[0], "ensemble_weight_lgbm": bundle.w_lgb, "train_base_rate": round(base, 5),
        "results_on_test": _results(bundle, y, parts, baselines, base),
        "feature_importance_lgbm_gain": dict(sorted(zip(bundle.feature_cols, map(float, bundle.lgb.booster_.feature_importance("gain"))), key=lambda kv: -kv[1])),
        "prior_mapping": f"p_false_closure = {PRIOR_LOW} + {PRIOR_SPAN} x risk percentile, so real-city priors stay in [0.30, 0.70]; NOT a calibrated probability",
        "caveats": [
            "The label is 'citizen reopened', a lower bound on false closure: it needs a persistent citizen and a department with a reopen workflow.",
            "Remark AND staff features are excluded: a reopened ticket gets a new remark and a senior handler, so both leak the label (a staff-role lookup alone scored AUROC 0.965).",
            "The reopen process drifts month to month: validation AUROC was far higher than test AUROC. Expect roughly the test figures, not the validation ones.",
            "This is a RANK score, not a probability: isotonic calibration on one slice made the next slice much worse (Brier skill -1.49), so none is applied.",
            "Ward-level only: no exact location or closing time exists for Bengaluru.",
        ],
    }
    sc = df[df["status"].isin(["closed", "reopened"]) & df["capable"]]       # only the regime the model was trained for
    p = core.predict_parts(bundle, sc)
    pct = pd.Series(p["ship"]).rank(pct=True).to_numpy()
    _write_scores("bengaluru", sc["ticket_id"], rank_prior(pct), "risk_rank_prior", bundle.name, pct)
    sc[["ticket_id"] + fb.CAT_COLS + fb.NUM_COLS].to_parquet(WAREHOUSE / "features_bengaluru.parquet", index=False)
    metrics["seconds"] = round(time.time() - t0, 1)
    _save(bundle.name, {"bundle": bundle}, metrics)
    return metrics


# ---------------------------------------------------------------- Mumbai (flags, no model)
def train_mumbai() -> dict:
    t0 = time.time()
    df = fm.build(pd.read_parquet(WAREHOUSE / "tickets_mumbai.parquet"))
    done = df["status"].isin(["closed", "reopened"]) & (df["location_precision"] == "exact")
    obs = df[done & df["label_observable"]].copy()
    split = pd.Timestamp("2026-08-01", tz="UTC")

    def effect(flag: str, part: pd.DataFrame) -> dict:
        f = part[part[flag].fillna(0) == 1]
        if len(f) < 20:
            return {"n_flagged": int(len(f)), "note": "too few flagged tickets to measure"}
        cols = fm.DENSITY_COLS + fm.TIME_COLS
        X = pd.get_dummies(part[cols + ["category"]], columns=["category"]).astype(float)
        X = (X - X.mean()) / X.std().replace(0, 1)
        X[flag] = part[flag].fillna(0).to_numpy()   # tickets without the field (pothole layer) count as not flagged
        yy = part["y"].to_numpy()
        j = list(X.columns).index(flag)
        beta = LogisticRegression(C=10, max_iter=500).fit(X, yy).coef_[0][j]
        rng, betas = np.random.default_rng(core.SEED), []
        for _ in range(100):
            i = rng.integers(0, len(X), len(X))
            if yy[i].min() == yy[i].max():
                continue
            betas.append(LogisticRegression(C=10, max_iter=300).fit(X.iloc[i], yy[i]).coef_[0][j])
        return {"n_flagged": int(len(f)), "observed_repeat_rate": round(float(f["y"].mean()), 3),
                "overall_repeat_rate": round(float(part["y"].mean()), 3),
                "odds_ratio_density_adjusted": round(float(np.exp(beta)), 2),
                "odds_ratio_ci95": [round(float(np.exp(np.percentile(betas, 2.5))), 2), round(float(np.exp(np.percentile(betas, 97.5))), 2)]}

    flags = {f: {"all_months": effect(f, obs), "held_out_aug_onward": effect(f, obs[obs["created_dt"] >= split])}
             for f in ("citizen_image_only", "fast_close")}
    # density-only vs everything: does anything beyond crowding predict the repeat label?
    sep = pd.Timestamp("2026-09-01", tz="UTC")
    tr, va, te = obs[obs.created_dt < split], obs[(obs.created_dt >= split) & (obs.created_dt < sep)], obs[obs.created_dt >= sep]
    cats = _cats(tr, fm.CAT_COLS)
    ablation = {}
    for name, cc, nums in (("density_only", ["category"], fm.DENSITY_COLS + fm.TIME_COLS), ("everything", fm.CAT_COLS, fm.NUM_COLS)):
        b = core.fit_ensemble("m", "m", tr, tr["y"].to_numpy(), va, va["y"].to_numpy(), cc, nums, {k: cats[k] for k in cc}, calibrate=False)
        pp = core.predict_parts(b, te)["ship"]
        ablation[name] = {"auroc": round(float(core.evaluate(te["y"].to_numpy(), pp, tr["y"].mean())["auroc"]), 4),
                          "auroc_ci95": core.bootstrap_auc(te["y"].to_numpy(), pp)}
    main = flags["citizen_image_only"]["all_months"]
    use_flag = main.get("odds_ratio_density_adjusted", 1.0) > 1 and main.get("odds_ratio_ci95", [0])[0] > 1
    flag_prior = float(min(main["odds_ratio_density_adjusted"] / (1 + main["odds_ratio_density_adjusted"]), FLAG_PRIOR_CAP)) if use_flag else 0.5

    sc = df[done]
    flagged = ((sc["citizen_image_only"] == 1).to_numpy()) & use_flag
    _write_scores("mumbai", sc["ticket_id"], np.where(flagged, flag_prior, 0.5), "rule_flags", "mum-flags-v1",
                  flags=np.where(flagged, "citizen_image_only", ""))
    metrics = {
        "model": "mum-flags-v1", "score_type": "rule_flags", "data_quality": "real (proxy label)",
        "label": "a repeat complaint of the same category in the same ~100 m cell, 24 h to 14 days after closure (proxy)",
        "flag_effects": flags, "ablation_test_auroc": ablation,
        "finding": "A density-only model reaches about the same AUROC as a model with every closure feature, so the repeat label mostly measures how crowded a spot is. No trained model is shipped for Mumbai.",
        "shipped_rule": {"flag": "citizen_image_only (closed with no attended photo, only the citizen's own)",
                         "prior_if_flagged": round(flag_prior, 3), "prior_otherwise": 0.5, "cap": FLAG_PRIOR_CAP, "used": bool(use_flag),
                         "why_not_fast_close": "no excess repeat rate over density (its odds-ratio interval includes 1)"},
        "caveats": ["Small samples (a few hundred flagged tickets); the held-out direction agrees but the interval is wide.",
                    "A repeat complaint can be a new problem or a neighbour reporting the same still-broken thing.",
                    "The flag is a risk prior, not proof of a false closure."],
        "seconds": round(time.time() - t0, 1),
    }
    _save("mum-flags-v1", {"flag_prior": flag_prior}, metrics)
    return metrics


# ---------------------------------------------------------------- synthetic
def train_synthetic() -> dict:
    t0 = time.time()
    pune = fs.build(pd.read_parquet(WAREHOUSE / "tickets_pune.parquet"), pd.read_parquet(WAREHOUSE / "truth_pune.parquet"))
    sbx = fs.build(pd.read_parquet(WAREHOUSE / "tickets_synthetic.parquet"), pd.read_parquet(WAREHOUSE / "truth_synthetic.parquet"))
    pc, sc_ = pune[pune["y"] >= 0], sbx[sbx["y"] >= 0]
    t_train, t_valid = pd.Timestamp("2024-08-01", tz="UTC"), pd.Timestamp("2024-10-01", tz="UTC")
    tr, va, te = pc[pc["created_dt"] < t_train], pc[(pc["created_dt"] >= t_train) & (pc["created_dt"] < t_valid)], pc[pc["created_dt"] >= t_valid]
    base = float(tr["y"].mean())
    bundle = core.fit_ensemble("syn-truth-v1", "ground-truth false closure in the synthetic generator", tr, tr["y"].to_numpy(), va, va["y"].to_numpy(),
                               fs.CAT_COLS, fs.NUM_COLS, _cats(tr, fs.CAT_COLS), calibrate=True)

    def block(part: pd.DataFrame) -> dict:
        y, parts = part["y"].to_numpy(), core.predict_parts(bundle, part)
        return {"results": _results(bundle, y, parts, {"baseline_category_rate": _rate_baseline(tr, part, ["category"], base)}, base),
                "reliability_shipped": core.reliability(y, parts["ship"])}
    metrics = {
        "model": bundle.name, "score_type": "calibrated_probability", "data_quality": "synthetic (ground truth by construction)",
        "label": bundle.label_definition, "WARNING": "SYNTHETIC INJECTION: these numbers measure how well the model recovers failure modes we injected, nothing more.",
        "splits": {"train": f"Pune, created before 2024-08-01 ({len(tr)} rows)", "validation": f"Pune, Aug-Sep 2024 ({len(va)} rows)",
                   "test_same_city_later": f"Pune, from 2024-10-01 ({len(te)} rows)", "test_unseen_city": f"Sandbox City, all months ({len(sc_)} rows)"},
        "shipped_model": bundle.ship, "validation_auroc": bundle.notes[0], "train_base_rate": round(base, 4),
        "test_pune_later_months": block(te), "test_sandbox_unseen_city": block(sc_),
        "feature_importance_lgbm_gain": dict(sorted(zip(bundle.feature_cols, map(float, bundle.lgb.booster_.feature_importance("gain"))), key=lambda kv: -kv[1])),
        "prior_clip": "p_false_closure is clipped to [0.02, 0.98] so the agent's evidence can still move a verdict",
        "caveats": ["Everything here is synthetic. The false-closure rate (about 21%) and the failure modes are invented by us.",
                    "Probabilities are calibrated for the synthetic world only; they say nothing about real cities."],
    }
    for city, df_all in (("pune", pune), ("synthetic", sbx)):
        closed = df_all[df_all["y"] >= 0]
        p = core.predict_parts(bundle, closed)["ship"]
        # isotonic saturates at 0/1; clip the PRIOR so the agent's evidence can still move a verdict
        _write_scores(city, closed["ticket_id"], np.clip(p, PRIOR_CLIP[0], PRIOR_CLIP[1]), "calibrated_probability", bundle.name,
                      pd.Series(p).rank(pct=True).to_numpy())
        closed[["ticket_id"] + fs.CAT_COLS + fs.NUM_COLS].to_parquet(WAREHOUSE / f"features_{city}.parquet", index=False)
    metrics["seconds"] = round(time.time() - t0, 1)
    _save(bundle.name, {"bundle": bundle}, metrics)
    return metrics


# ---------------------------------------------------------------- display
def show(m: dict) -> None:
    print("\n==", m["model"], "|", m.get("score_type"), "|", m.get("label"))
    if "WARNING" in m:
        print("  !!", m["WARNING"])

    def table(res: dict) -> None:
        print(f"    {'model':34s} {'AUROC':>7s} {'95% CI':>16s} {'PR-AUC':>8s} {'Brier skill':>11s} {'lift@1%':>8s} {'lift@10%':>9s}")
        for k, r in res.items():
            print(f"    {k:34s} {r['auroc']:7.3f} {str(r['auroc_ci95']):>16s} {r['pr_auc']:8.4f} {r['brier_skill_vs_train_rate']:11.3f} "
                  f"{r['lift_top1pct']['lift']:8.1f} {r['lift_top10pct']['lift']:9.2f}")
    if "results_on_test" in m:
        for k, v in m["splits"].items():
            print("  ", k, v)
        print("  shipped:", m["shipped_model"], "|", m["validation_auroc"])
        table(m["results_on_test"])
    if "test_pune_later_months" in m:
        for k, v in m["splits"].items():
            print("  ", k, v)
        print("  shipped:", m["shipped_model"], "|", m["validation_auroc"])
        print("  -- Pune, later months"); table(m["test_pune_later_months"]["results"])
        print("  -- Sandbox City (unseen)"); table(m["test_sandbox_unseen_city"]["results"])
        print("  top features:", list(m["feature_importance_lgbm_gain"])[:6])
    if "flag_effects" in m:
        print("  flag effects:", json.dumps(m["flag_effects"], indent=2))
        print("  ablation (test AUROC):", m["ablation_test_auroc"])
        print("  shipped rule:", m["shipped_rule"])


TRAINERS = {"bengaluru": train_bengaluru, "mumbai": train_mumbai, "pune": train_synthetic}

if __name__ == "__main__":
    names = sys.argv[1:] or ["bengaluru"]
    for name in (list(TRAINERS) if names == ["all"] else names):
        if name not in TRAINERS:
            sys.exit(f"unknown scorer {name!r}; choose from {sorted(TRAINERS)} or 'all'")
        show(TRAINERS[name]())
