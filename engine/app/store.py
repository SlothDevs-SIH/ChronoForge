"""Fixture-backed store. SOHAM: replace load_* with the DuckDB/Parquet feature store as modules land."""
import json
import os
from pathlib import Path

from .models import Score, Ticket

CONTRACT_DIR = Path(os.environ.get("CONTRACT_DIR", Path(__file__).resolve().parents[2] / "contract"))


def _load(name: str):
    return json.loads((CONTRACT_DIR / name).read_text(encoding="utf-8"))


class Store:
    def __init__(self) -> None:
        self.tickets: dict[str, Ticket] = {t["ticket_id"]: Ticket(**t) for t in _load("tickets.json")}
        self.scores: dict[str, Score] = {k: Score(**v) for k, v in _load("scores.json").items()}
        self.ward_stats: list[dict] = _load("ward_stats.json")
        self.eval_results: dict = _load("eval_results.json")
        self.evidence_templates: dict = _load("evidence.json")


store = Store()
