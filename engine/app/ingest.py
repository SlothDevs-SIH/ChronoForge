"""Run a connector and write its tickets to Parquet in data/warehouse/ (gitignored), plus a drop report.

Usage (from engine/):   python -m app.ingest mumbai
"""
import json
import sys
from pathlib import Path

import pandas as pd

from .connectors.base import ComplaintSource
from .connectors.mumbai import MumbaiSource

DATA = Path(__file__).resolve().parents[2] / "data"
SOURCES = {"mumbai": lambda: MumbaiSource(DATA / "raw")}


def ingest(source: ComplaintSource, out_dir: Path = DATA / "warehouse") -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(list(source.tickets()))
    df.to_parquet(out_dir / f"tickets_{source.city}.parquet", index=False)
    report = dict(source.report)
    (out_dir / f"tickets_{source.city}.report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return df


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "mumbai"
    if name not in SOURCES:
        sys.exit(f"unknown source {name!r}; choose from {sorted(SOURCES)}")
    src = SOURCES[name]()
    df = ingest(src)
    print(f"{name}: kept {len(df)} tickets")
    for k, v in sorted(src.report.items()):
        print(f"  {k}: {v}")
