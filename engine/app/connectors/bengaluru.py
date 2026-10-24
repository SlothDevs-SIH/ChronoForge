"""Bengaluru connector: BBMP grievances 2020 to mid-2025 (OpenCity yearly CSVs).

What the data has and lacks (measured, see data/README.md):
- Columns: Complaint ID, Category, Sub Category, Grievance Date, Ward Name, Grievance Status, Staff Remarks, Staff Name.
- NO coordinates and NO closing time. Location is the ward only, so lat/lng are the ward CENTROID (for map display)
  with location_precision="ward_centroid", h3 is None, and closed_at is None for closed tickets.
  Nothing that needs a real point (satellite check, 100 m repeat features) may use these tickets.
- Grievance Date is naive local time; we treat it as IST (UTC+5:30) and convert to UTC. This is an assumption.
- Status: Closed and Resolved are closed; ReOpen is reopened; Registered, In Progress, Long Term Solution are open;
  Rejected, Non Relevant and null are dropped.
- Staff names are hashed. The role after the last "/" (AEE, JHI, AE, ...) is kept as staff_role.
"""
import csv
import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, Optional

from .base import ComplaintSource, Drop

IST = timedelta(hours=5, minutes=30)
CLOSED = {"closed", "resolved"}
OPEN = {"registered", "in progress", "long term solution"}
DROPPED = {"rejected", "non relevant", "null", ""}


def category(cat: str, sub: str) -> str:
    c, s = (cat or "").lower(), (sub or "").lower()
    if "street light" in s and "requirement" not in s or "park lights" in s:
        return "streetlight"
    if s == "potholes":
        return "pothole"
    if c.startswith("storm") or s in ("road side drains", "water stagnation", "maintenance of swd",
                                      "sewerage water left in swd", "garbage thrown in storm water drain"):
        return "drain"
    if c.startswith("solid waste") or "debris removal" in s:
        return "garbage"
    return "other"


def _utc(naive: str) -> Optional[str]:
    try:
        return (datetime.fromisoformat(naive[:19]) - IST).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _norm(remark: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (remark or "").lower()).strip()


class BengaluruSource(ComplaintSource):
    name = "bbmp_opencity"
    city = "bengaluru"

    def __init__(self, raw_dir: Path, ward_map: Path, years: range = range(2020, 2026)) -> None:
        super().__init__()
        self.raw_dir, self.years = raw_dir, years
        with ward_map.open(encoding="utf-8", newline="") as f:
            self._wards = {r["complaint_ward_name"]: r for r in csv.DictReader(f)}
        self._seen: set[str] = set()

    def fetch(self) -> Iterator[dict[str, Any]]:
        for year in self.years:
            path = self.raw_dir / f"bbmp_{year}.csv"
            with path.open(encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    row["_year"] = year
                    yield row

    def normalise(self, r: dict[str, Any]) -> dict[str, Any]:
        status_raw = (r["Grievance Status"] or "").strip().lower()
        if status_raw in DROPPED:
            raise Drop(f"status_{status_raw or 'blank'}".replace(" ", "_"))
        if status_raw not in CLOSED | OPEN | {"reopen"}:
            raise Drop(f"unknown_status:{status_raw}")
        cid = r["Complaint ID"].strip()
        if cid in self._seen:
            raise Drop("duplicate_id")
        created = _utc(r["Grievance Date"])
        if not created:
            raise Drop("bad_created_date")
        ward = (r["Ward Name"] or "").strip()
        if not ward:
            raise Drop("missing_ward")
        self._seen.add(cid)

        w = self._wards.get(ward)
        has_pt = bool(w and w["centroid_lat"])
        staff = (r["Staff Name"] or "").strip()
        staff_ok = staff and staff.lower() != "null"
        remark = (r["Staff Remarks"] or "").strip()
        sub = r["Sub Category"].strip()
        status = "reopened" if status_raw == "reopen" else ("closed" if status_raw in CLOSED else "open")
        return {
            "ticket_id": f"blr-{cid}", "city": self.city, "data_quality": "partial", "source": self.name,
            "category": category(r["Category"], sub), "text": sub or r["Category"].strip(), "lang": "other",
            "lat": float(w["centroid_lat"]) if has_pt else None, "lng": float(w["centroid_lng"]) if has_pt else None,
            "h3": None, "ward": ward, "created_at": created, "closed_at": None,
            "closed_by_hash": hashlib.sha1(staff.lower().encode()).hexdigest()[:8] if staff_ok else None,
            "status": status, "closure_note": remark if status != "open" and remark else None, "closure_photo_url": None,
            # extras
            "location_precision": "ward_centroid" if has_pt else "none",
            "ward_zone": (w["zone"] or None) if w else None,
            "raw_category": r["Category"].strip(), "raw_status": r["Grievance Status"].strip(),
            "staff_role": staff.rsplit("/", 1)[-1].strip() if staff_ok and "/" in staff else None,
            "remark_norm": _norm(remark) if status != "open" else None,
            "remark_blank_like": (len(re.sub(r"[^A-Za-z0-9]", "", remark)) <= 1) if status != "open" else None,
            "source_year": r["_year"],
        }
