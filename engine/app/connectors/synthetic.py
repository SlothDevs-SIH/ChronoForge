"""Synthetic connector: Pune (synthetic complaints on real Pune geography) and Sandbox City (fully fictional).

Input is the output of data/scripts/make_synthetic.py. Ground-truth columns (gt_*) are NOT put on the ticket:
they go to self.truth, which ingest writes to a separate truth_<city>.parquet. Scorer features must never read it;
only the benchmark may. Everything here is synthetic and the tickets say so (data_quality="synthetic").
"""
import csv
from pathlib import Path
from typing import Any, Iterator

from .base import ComplaintSource, Drop

GT = ("gt_false_closure", "gt_failure_mode", "gt_site_changed")


class SyntheticSource(ComplaintSource):
    name = "synthetic_generator"

    def __init__(self, csv_path: Path, city: str) -> None:
        super().__init__()
        self.path, self.city = csv_path, city

    def fetch(self) -> Iterator[dict[str, Any]]:
        with self.path.open(encoding="utf-8", newline="") as f:
            yield from csv.DictReader(f)

    def normalise(self, r: dict[str, Any]) -> dict[str, Any]:
        if r["city"] != self.city:
            raise Drop("wrong_city")
        if r["status"] not in ("open", "closed", "reopened"):
            raise Drop(f"unknown_status:{r['status']}")
        if r["status"] != "open" and not r["closed_at"]:
            raise Drop("closed_without_time")
        if r["gt_false_closure"] != "":
            self.truth.append({"ticket_id": r["ticket_id"], "gt_false_closure": int(r["gt_false_closure"]),
                               "gt_failure_mode": r["gt_failure_mode"], "gt_site_changed": int(r["gt_site_changed"])})
        closed = r["status"] != "open"
        return {
            "ticket_id": r["ticket_id"], "city": self.city, "data_quality": "synthetic", "source": self.name,
            "category": r["category"], "text": r["text"], "lang": r["lang"],
            "lat": float(r["lat"]), "lng": float(r["lng"]), "h3": r["h3"], "ward": r["ward"],
            "created_at": r["created_at"], "closed_at": r["closed_at"] or None,
            "closed_by_hash": r["closed_by_hash"] or None, "status": r["status"],
            "closure_note": r["closure_note"] or None, "closure_photo_url": None,
            # extras
            "location_precision": "generated", "closing_basis": "generated" if closed else None,
            "closure_photo_id": r["closure_photo_id"] or None,
            "closure_photo_exif_dist_m": float(r["closure_photo_exif_dist_m"]) if r["closure_photo_exif_dist_m"] else None,
        }
