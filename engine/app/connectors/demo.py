"""Demo connector: the labelled demo photo set (demo/photos/manifest.json) as closed tickets, so the whole loop can
be shown on tickets that actually carry closure photos (Mumbai rows only have photo file names).

Every ticket is data_quality "synthetic" in city "synthetic": the photo content is real open-licence imagery
(see demo/photos/ATTRIBUTION.md) but the tickets, their EXIF location/time and the planted failures
(reused photo, wrong location, stale timestamp, scene still broken) are demo data. Written to tickets_demo.parquet
(file_stem) so it never overwrites the Sandbox City file.
"""
import json
from pathlib import Path
from typing import Any, Iterator

from .base import ComplaintSource

DEMO_DIR = Path(__file__).resolve().parents[3] / "demo" / "photos"
TEXT = {"pothole": "Pothole on the road surface.", "garbage": "Garbage dumped on the street."}


class DemoSource(ComplaintSource):
    name = "demo_photo_set"
    city = "synthetic"
    file_stem = "demo"

    def __init__(self, directory: Path = DEMO_DIR) -> None:
        super().__init__()
        self.dir = directory

    def fetch(self) -> Iterator[dict[str, Any]]:
        yield from json.loads((self.dir / "manifest.json").read_text(encoding="utf-8"))

    def normalise(self, r: dict[str, Any]) -> dict[str, Any]:
        return {
            "ticket_id": r["ticket_id"], "city": "synthetic", "data_quality": "synthetic", "source": self.name,
            "category": r["category"], "text": TEXT.get(r["category"], "Civic issue."), "lang": "en",
            "lat": r["lat"], "lng": r["lng"], "h3": None, "location_precision": "generated", "ward": "Demo Ward",
            "created_at": "2026-10-01T10:00:00Z", "closed_at": r["closed_at"], "closed_by_hash": None,
            "status": "closed", "closure_note": "Work completed.",
            "closure_photo_url": f"demo/photos/{r['after']}",
            # extras (the API model ignores them)
            "complaint_photo_url": f"demo/photos/{r['before']}", "demo_plan": r["plan"],
        }
