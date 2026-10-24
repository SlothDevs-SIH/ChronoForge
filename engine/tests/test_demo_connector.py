import json
from pathlib import Path

import pandas as pd
import pytest

from app.connectors.demo import DemoSource
from app.ingest import ingest

REAL_MANIFEST = Path(__file__).resolve().parents[2] / "demo" / "photos" / "manifest.json"


def entry(**kw):
    e = {"ticket_id": "DEMO-000", "category": "pothole", "lat": 12.9, "lng": 77.55, "closed_at": "2026-10-21T09:00:00Z",
         "before": "planted/DEMO-000_before.jpg", "after": "planted/DEMO-000_after.jpg", "plan": "clean", "planted_failure": False}
    e.update(kw)
    return e


def make(tmp_path, entries):
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    src = DemoSource(p)
    return src, {t["ticket_id"]: t for t in src.tickets()}


def test_demo_tickets_are_labelled_synthetic_and_carry_repo_relative_photo_paths(tmp_path):
    _, t = make(tmp_path, [entry()])
    x = t["DEMO-000"]
    assert x["data_quality"] == "synthetic" and x["city"] == "demo" and x["location_precision"] == "generated"
    assert x["closure_photo_url"] == "demo/photos/planted/DEMO-000_after.jpg"
    assert x["complaint_photo_url"] == "demo/photos/planted/DEMO-000_before.jpg"
    assert x["status"] == "closed" and x["created_at"] < x["closed_at"] and x["h3"]


def test_planted_failures_are_ground_truth_and_never_on_the_ticket(tmp_path):
    src, t = make(tmp_path, [entry(), entry(ticket_id="DEMO-003", plan="reused", planted_failure=True)])
    assert not [k for k in t["DEMO-003"] if k.startswith("gt_") or k == "plan" or k == "planted_failure"]
    truth = {r["ticket_id"]: r for r in src.truth}
    assert truth["DEMO-003"]["gt_false_closure"] == 1 and truth["DEMO-003"]["gt_failure_mode"] == "reused"
    assert truth["DEMO-000"]["gt_false_closure"] == 0 and truth["DEMO-000"]["gt_failure_mode"] == "none"


@pytest.mark.parametrize("missing", ["after", "before", "lat", "closed_at"])
def test_incomplete_entries_are_dropped_with_a_reason(tmp_path, missing):
    src, t = make(tmp_path, [entry(**{missing: None})])
    assert t == {} and src.report[f"dropped:missing_{missing}"] == 1


def test_ingest_writes_a_separate_truth_file(tmp_path):
    src, _ = make(tmp_path, [entry(planted_failure=True, plan="shifted_gps")])
    df = ingest(DemoSource(tmp_path / "manifest.json"), tmp_path / "wh")
    assert "complaint_photo_url" in df.columns and not [c for c in df.columns if c.startswith("gt_")]
    assert pd.read_parquet(tmp_path / "wh" / "truth_demo.parquet").loc[0, "gt_failure_mode"] == "shifted_gps"


@pytest.mark.skipif(not REAL_MANIFEST.exists(), reason="demo manifest not present")
def test_every_photo_in_the_real_manifest_exists_and_the_set_has_every_planted_kind():
    src = DemoSource(REAL_MANIFEST)
    tickets = list(src.tickets())
    root = REAL_MANIFEST.parents[2]
    assert len(tickets) == 12 and src.report["kept"] == 12
    for t in tickets:
        assert (root / t["closure_photo_url"]).exists() and (root / t["complaint_photo_url"]).exists(), t["ticket_id"]
    modes = {r["gt_failure_mode"] for r in src.truth}
    assert {"reused", "shifted_gps", "stale_time", "still_broken", "none"} <= modes
