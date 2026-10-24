"""Run a connector and write its tickets to Parquet in data/warehouse/ (gitignored), plus a drop report.
Synthetic sources also write truth_<city>.parquet (ground truth, benchmark use only).

Usage (from engine/):   python -m app.ingest mumbai|bengaluru|pune|synthetic|demo|all
"""
import json
import os
import sys
from pathlib import Path

import pandas as pd

from .connectors.base import ComplaintSource
from .connectors.bengaluru import BengaluruSource
from .connectors.demo import DemoSource
from .connectors.mumbai import MumbaiSource
from .connectors.synthetic import SyntheticSource

DATA = Path(__file__).resolve().parents[2] / "data"
SOURCES = {
    "mumbai": lambda: MumbaiSource(DATA / "raw"),
    "bengaluru": lambda: BengaluruSource(DATA / "raw", DATA / "processed" / "bengaluru_ward_name_map.csv"),
    "pune": lambda: SyntheticSource(DATA / "processed" / "synthetic_pune.csv", "pune"),
    "synthetic": lambda: SyntheticSource(DATA / "processed" / "synthetic_city.csv", "synthetic"),
    "demo": lambda: DemoSource(DATA.parent / "demo" / "photos" / "manifest.json"),
}


def ingest(source: ComplaintSource, out_dir: Path | None = None) -> pd.DataFrame:
    """Writes into out_dir, else $WAREHOUSE_DIR, else data/warehouse. Re-running replaces the same files (idempotent);
    municipal status changes live in status_overrides.json, which this never touches."""
    out_dir = out_dir or Path(os.environ.get("WAREHOUSE_DIR", DATA / "warehouse"))
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(list(source.tickets()))
    df.to_parquet(out_dir / f"tickets_{source.city}.parquet", index=False)
    if source.truth:
        pd.DataFrame(source.truth).to_parquet(out_dir / f"truth_{source.city}.parquet", index=False)
    (out_dir / f"tickets_{source.city}.report.json").write_text(
        json.dumps(dict(source.report), indent=2, sort_keys=True), encoding="utf-8")
    return df


if __name__ == "__main__":
    names = sys.argv[1:] or ["mumbai"]
    if names == ["all"]:
        names = list(SOURCES)
    for name in names:
        if name not in SOURCES:
            sys.exit(f"unknown source {name!r}; choose from {sorted(SOURCES)} or 'all'")
        src = SOURCES[name]()
        df = ingest(src)
        print(f"{name}: kept {len(df)} tickets")
        for k, v in sorted(src.report.items()):
            print(f"  {k}: {v}")
