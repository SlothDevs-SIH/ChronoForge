import json

from app.connectors.demo import DemoSource
from app.ingest import ingest


def manifest(tmp_path):
    rows = [{"ticket_id": "DEMO-000", "category": "pothole", "lat": 12.9, "lng": 77.55,
             "closed_at": "2026-10-21T09:00:00Z", "before": "planted/DEMO-000_before.jpg",
             "after": "planted/DEMO-000_after.jpg", "plan": "clean", "planted_failure": False}]
    (tmp_path / "manifest.json").write_text(json.dumps(rows))
    return tmp_path


def test_demo_tickets_carry_closure_photos_and_are_labelled_synthetic(tmp_path):
    src = DemoSource(manifest(tmp_path))
    t = next(src.tickets())
    assert t["closure_photo_url"] == "demo/photos/planted/DEMO-000_after.jpg"
    assert t["data_quality"] == "synthetic" and t["status"] == "closed" and t["location_precision"] == "generated"
    assert t["complaint_photo_url"].endswith("DEMO-000_before.jpg")


def test_demo_ingest_does_not_overwrite_the_sandbox_city_file(tmp_path):
    out = tmp_path / "wh"
    ingest(DemoSource(manifest(tmp_path)), out)
    assert (out / "tickets_demo.parquet").exists() and not (out / "tickets_synthetic.parquet").exists()
