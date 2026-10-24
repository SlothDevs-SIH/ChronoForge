"""Demo connector: the planted-failure photo set built for the live demo (demo/photos/manifest.json, by Ayush).

Real: the photo CONTENT (open-licence Wikimedia Commons images, credited in demo/photos/ATTRIBUTION.md).
Invented: everything else. The EXIF location and time written onto the photos, the tickets, their dates and the planted
failures are synthetic, and the tickets say so (data_quality="synthetic"). Each planted failure is ground truth: it goes to
self.truth (a separate file) and never onto the ticket.

These tickets exist so the real photo verifier has photos to check once the Engine serves the warehouse: without them none
of the real tickets carries a closure photo. Photo paths are repo-relative, which is how the Agent resolves them.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

import h3

from .base import ComplaintSource, Drop

TEXT = {"pothole": "Demo ticket: pothole closed with a photo (planted-failure set)",
        "garbage": "Demo ticket: garbage closed with a photo (planted-failure set)"}


class DemoSource(ComplaintSource):
    name = "demo_set"
    city = "demo"

    def __init__(self, manifest: Path, photo_root: str = "demo/photos") -> None:
        super().__init__()
        self.manifest, self.photo_root = manifest, photo_root

    def fetch(self) -> Iterator[dict[str, Any]]:
        yield from json.loads(self.manifest.read_text(encoding="utf-8"))

    def normalise(self, e: dict[str, Any]) -> dict[str, Any]:
        for key in ("ticket_id", "category", "lat", "lng", "closed_at", "before", "after"):
            if e.get(key) in (None, ""):
                raise Drop(f"missing_{key}")
        closed = datetime.fromisoformat(e["closed_at"].replace("Z", "+00:00"))
        created = closed - timedelta(days=2)       # invented: the manifest only carries the closing time
        failure = bool(e.get("planted_failure"))
        self.truth.append({"ticket_id": e["ticket_id"], "gt_false_closure": int(failure),
                           "gt_failure_mode": e.get("plan", "none") if failure else "none", "gt_site_changed": 0 if failure else 1})
        iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "ticket_id": e["ticket_id"], "city": self.city, "data_quality": "synthetic", "source": self.name,
            "category": e["category"], "text": TEXT.get(e["category"], "Demo ticket"), "lang": "en",
            "lat": float(e["lat"]), "lng": float(e["lng"]), "h3": h3.latlng_to_cell(float(e["lat"]), float(e["lng"]), 9),
            "ward": "Demo Ward", "created_at": iso(created), "closed_at": iso(closed), "closed_by_hash": "demo0001",
            "status": "closed", "closure_note": None,
            "closure_photo_url": f"{self.photo_root}/{e['after']}", "complaint_photo_url": f"{self.photo_root}/{e['before']}",
            "location_precision": "generated", "closing_basis": "generated",
        }
