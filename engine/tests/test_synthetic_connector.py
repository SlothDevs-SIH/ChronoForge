import csv

import pandas as pd

from app.connectors.synthetic import SyntheticSource
from app.ingest import ingest

FIELDS = ["ticket_id", "city", "data_quality", "source", "category", "text", "lang", "lat", "lng", "h3", "ward",
          "created_at", "closed_at", "closed_by_hash", "status", "closure_note", "closure_photo_id",
          "closure_photo_exif_dist_m", "gt_false_closure", "gt_failure_mode", "gt_site_changed"]


def r(**kw):
    base = dict.fromkeys(FIELDS, "")
    base.update(ticket_id="pune-000001", city="pune", data_quality="synthetic", source="synthetic_generator",
                category="drain", text="Drain is blocked.", lang="en", lat="18.5", lng="73.85", h3="8960885016bffff",
                ward="Kasba", created_at="2024-06-01T08:00:00Z", closed_at="2024-06-01T08:20:00Z",
                closed_by_hash="abc123", status="closed", closure_note=".", closure_photo_id="ph-pune-000001",
                closure_photo_exif_dist_m="1200.5", gt_false_closure="1", gt_failure_mode="fast_close+no_work",
                gt_site_changed="0")
    base.update(kw)
    return base


def make(tmp_path, rows, city="pune"):
    path = tmp_path / "s.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    src = SyntheticSource(path, city)
    return src, {t["ticket_id"]: t for t in src.tickets()}


def test_ticket_is_labelled_synthetic_with_generated_location(tmp_path):
    _, t = make(tmp_path, [r()])
    x = t["pune-000001"]
    assert x["data_quality"] == "synthetic" and x["location_precision"] == "generated"
    assert x["closure_photo_exif_dist_m"] == 1200.5 and x["closure_photo_id"] == "ph-pune-000001"


def test_ground_truth_never_appears_on_the_ticket(tmp_path):
    src, t = make(tmp_path, [r()])
    assert not [k for k in t["pune-000001"] if k.startswith("gt_")]
    assert src.truth == [{"ticket_id": "pune-000001", "gt_false_closure": 1, "gt_failure_mode": "fast_close+no_work",
                          "gt_site_changed": 0}]


def test_open_ticket_and_drop_rules(tmp_path):
    src, t = make(tmp_path, [
        r(ticket_id="pune-000002", status="open", closed_at="", gt_false_closure="", gt_failure_mode="", gt_site_changed=""),
        r(ticket_id="pune-000003", closed_at=""),
        r(ticket_id="pune-000004", city="synthetic"),
    ])
    assert set(t) == {"pune-000002"} and t["pune-000002"]["closed_at"] is None and t["pune-000002"]["closing_basis"] is None
    assert src.report["dropped:closed_without_time"] == 1 and src.report["dropped:wrong_city"] == 1
    assert src.truth == []  # open tickets have no ground truth


def test_ingest_writes_truth_to_a_separate_file(tmp_path):
    src, _ = make(tmp_path, [r()])
    src2 = SyntheticSource(tmp_path / "s.csv", "pune")
    df = ingest(src2, tmp_path / "wh")
    assert len(df) == 1 and not [c for c in df.columns if c.startswith("gt_")]
    truth = pd.read_parquet(tmp_path / "wh" / "truth_pune.parquet")
    assert truth.loc[0, "gt_false_closure"] == 1
