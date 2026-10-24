"""Request-time explanations. Loads a trained bundle once and explains one ticket from its stored feature row.

Reasons come from the LightGBM component's TreeSHAP values (log-odds), whichever model is shipped, because tree SHAP is
exact and cheap. For a rule flag the reason is the flag with ln(odds ratio) measured in training.
"""
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Optional

import duckdb
import joblib

from . import core

ROOT = Path(__file__).resolve().parents[3]
MODELS = ROOT / "data" / "models"

BUNDLE_FILES = {"blr-reopen-v1": "blr-reopen-v1.joblib", "syn-truth-v1": "syn-truth-v1.joblib"}
CITY_FEATURES = {"bengaluru": "features_bengaluru.parquet", "pune": "features_pune.parquet",
                 "synthetic": "features_synthetic.parquet"}


@lru_cache(maxsize=4)
def _bundle(version: str):
    path = MODELS / BUNDLE_FILES[version]
    return joblib.load(path)["bundle"] if path.exists() else None


@lru_cache(maxsize=1)
def _flag_log_or() -> float:
    path = MODELS / "mum-flags-v1.metrics.json"
    if not path.exists():
        return 0.0
    m = json.loads(path.read_text(encoding="utf-8"))
    return math.log(m["flag_effects"]["citizen_image_only"]["all_months"]["odds_ratio_density_adjusted"])


def reasons(ticket_id: str, city: str, model_version: Optional[str], flags: str, warehouse: Path, top: int = 3) -> list[dict]:
    if model_version == "mum-flags-v1":
        return [{"feature": f, "value": 1.0, "shap": round(_flag_log_or(), 3)} for f in flags.split(",") if f]
    if model_version not in BUNDLE_FILES or city not in CITY_FEATURES:
        return []
    bundle = _bundle(model_version)
    path = warehouse / CITY_FEATURES[city]
    if bundle is None or not path.exists():
        return []
    row = duckdb.connect().execute("select * from read_parquet(?) where ticket_id = ?", [str(path), ticket_id]).df()
    return core.explain(bundle, row, top)[0] if len(row) else []
