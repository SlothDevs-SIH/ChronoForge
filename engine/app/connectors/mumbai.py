"""Mumbai connector: BMC MARG complaints (layer 0) enriched with the pothole layer (layer 16).

Raw files come from data/scripts/download_mumbai.py. Facts this code relies on (measured, see data/README.md):
- 12,473 of the 12,492 pothole-layer ids also exist in layer 0, so the pothole layer ENRICHES those tickets
  (real RESOLVED_DATE, post-work photo flag, reopen) and only the remaining ones are added as new tickets.
- Closing time: the pothole layer's RESOLVED_DATE if present, else layer 0 RESOLVED_DATE, else AFTER_IMAGE_DATE
  (the date of the attended image, a proxy for closure and not a formal closing timestamp).
- 15,526 complaints share one placeholder coordinate and are dropped. INVALID=YES and DISCARDED are dropped.
- Image columns hold file names only, so closure_photo_url is None. The file names still tell us whether an
  attended photo was uploaded, which becomes has_attended_image / citizen_image_only.
Free text and citizen identifiers are never read: the download script does not fetch them.
"""
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

import h3

from .base import ComplaintSource, Drop

PLACEHOLDER = ("19.07766361", "72.87740978")
BBOX = (18.85, 19.35, 72.75, 73.05)  # lat_min, lat_max, lng_min, lng_max (Mumbai region)
CITIZEN_ONLY_IMAGE = "Initial Image By Citizen.jpg"
OPEN_STATUSES = {"IN PROGRESS", "IN REVIEW", "NEW"}


def category(type_: str, name: str) -> str:
    """Map by complaint NAME first: the same name appears under several types (street lights under Solid Waste)."""
    n, t = (name or "").lower(), (type_ or "").lower()
    if "encro" in n or t == "encroachment":
        return "other"  # "Encrochment ... footpath / drains" mentions drains but is not a drain fault
    if "pothole" in n or "re-surfacing of roads" in n:
        return "pothole"  # road-surface damage; the contract has no separate road_repair category
    if "street light" in n:
        return "streetlight"
    if "leak" in n or "burst water" in n:
        return "water_leak"
    if "drain" in n or "manhole" in n or "sewer" in n or t in ("drainage", "storm water drain", "sewerage operation"):
        return "drain"
    if "garbage" in n or "debris" in n or "dustbin" in n or "swept" in n or t == "solid waste management":
        return "garbage"
    return "other"


def _iso(value: str) -> Optional[str]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _dt(iso: str) -> datetime:
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")


def _read(path: Path) -> Iterator[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


class MumbaiSource(ComplaintSource):
    name = "mumbai_marg"
    city = "mumbai"

    def __init__(self, raw_dir: Path) -> None:
        super().__init__()
        self.complaints = raw_dir / "mumbai_marg_complaints.csv"
        self.potholes = raw_dir / "mumbai_marg_potholes.csv"
        self._pot: dict[str, dict[str, str]] = {p["COMPLAINTS_ID"]: p for p in _read(self.potholes)}
        self._seen: set[str] = set()

    # ---- fetch: complaints first, then pothole rows that layer 0 does not have ----
    def fetch(self) -> Iterator[dict[str, Any]]:
        for row in _read(self.complaints):
            self._seen.add(row["COMPLAINT_ID"])
            yield {"layer": 0, "row": row, "pothole": self._pot.get(row["COMPLAINT_ID"])}
        for pid, p in self._pot.items():
            if pid not in self._seen:
                yield {"layer": 16, "row": p, "pothole": p}

    # ---- normalise ----
    def normalise(self, raw: dict[str, Any]) -> dict[str, Any]:
        return self._from_complaint(raw["row"], raw["pothole"]) if raw["layer"] == 0 else self._from_pothole(raw["row"])

    def _common(self, lat_s: str, lng_s: str) -> tuple[float, float, str]:
        if (lat_s, lng_s) == PLACEHOLDER:
            raise Drop("placeholder_location")
        try:
            lat, lng = float(lat_s), float(lng_s)
        except ValueError:
            raise Drop("missing_coordinates")
        if not (BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lng <= BBOX[3]):
            raise Drop("outside_mumbai")
        return lat, lng, h3.latlng_to_cell(lat, lng, 9)

    def _finish(self, t: dict[str, Any]) -> dict[str, Any]:
        # A reopened ticket was closed once; keep its earlier closing time if we have one, but do not require it.
        if t["closed_at"]:
            if _dt(t["closed_at"]) < _dt(t["created_at"]):
                raise Drop("closed_before_created")
            t["res_hours"] = round((_dt(t["closed_at"]) - _dt(t["created_at"])).total_seconds() / 3600, 3)
        elif t["status"] == "closed":
            raise Drop("closed_without_time")
        else:
            t["res_hours"] = None
        return t

    def _from_complaint(self, r: dict[str, str], pot: Optional[dict[str, str]]) -> dict[str, Any]:
        status_raw = r["COMPLAINT_STATUS"].strip().upper()
        if status_raw == "DISCARDED":
            raise Drop("discarded_status")
        if r["INVALID"] == "YES" or (pot and pot.get("SUBSTATUS") == "Invalid"):
            raise Drop("invalid_complaint")
        if status_raw not in OPEN_STATUSES | {"CLOSED"}:
            raise Drop(f"unknown_status:{status_raw}")
        created = _iso(r["COMP_REG_DATE"])
        if not created:
            raise Drop("missing_created")
        lat, lng, cell = self._common(r["COMPLAINT_REG_LATITUDE"], r["COMPLAINT_REG_LONGITUDE"])
        if not r["COMPLAINT_REG_WARD"]:
            raise Drop("missing_ward")

        closed = status_raw == "CLOSED"
        reopened = bool(pot and (pot.get("REOPEN_STATUS") == "Y" or pot.get("SUBSTATUS") == "Reopen"))
        closed_at, basis = None, None
        if closed or reopened:
            for iso, b in ((_iso(pot["RESOLVED_DATE"]) if pot else None, "pothole_resolved_date"),
                           (_iso(r["RESOLVED_DATE"]), "resolved_date"),
                           (_iso(r["AFTER_IMAGE_DATE"]), "after_image_date")):
                if iso:
                    closed_at, basis = iso, b
                    break
        after = r["AFTER_IMAGE"].strip()
        attended = "attended" in after.lower() or bool(pot and pot.get("CONFIRM_POSTWORK_IMAGE") == "Yes")
        status = "reopened" if reopened else ("closed" if closed else "open")
        name = r["COMPLAINT_NAME"]
        return self._finish({
            "ticket_id": f"mum-{r['COMPLAINT_ID']}", "city": self.city, "data_quality": "real", "source": self.name,
            "category": category(r["COMPLAINT_TYPE"], name),
            "text": name or r["COMPLAINT_TYPE"], "lang": "other",
            "lat": round(lat, 6), "lng": round(lng, 6), "h3": cell, "ward": r["COMPLAINT_REG_WARD"],
            "created_at": created, "closed_at": closed_at, "closed_by_hash": r["GROUND_STAFF"] or r["CO_EMP_ID"] or None,
            "status": status, "closure_note": r["L1_REMARKS"] or r["ATTENDED"] or None, "closure_photo_url": None,
            # extra real signals
            "complaint_type": r["COMPLAINT_TYPE"], "zone": r["COMPLAINT_ZONE"] or None, "channel": r["COMPLAINT_SOURCE"] or None,
            "escalated": {"YES": True, "NO": False}.get(r["ESCALATED_NEW"]),
            "closing_basis": basis,
            "has_attended_image": attended if closed else None,
            "citizen_image_only": (after == CITIZEN_ONLY_IMAGE and not attended) if closed else None,
            "from_pothole_layer": pot is not None,
        })

    def _from_pothole(self, p: dict[str, str]) -> dict[str, Any]:
        if p["SUBSTATUS"] == "Invalid":
            raise Drop("invalid_complaint")
        created = _iso(p["COMPLAINTS_CREATION_DATE"])
        if not created:
            raise Drop("missing_created")
        lat, lng, cell = self._common(p["LATITUDE"], p["LONGITUDE"])
        if not p["WARD_NAME"]:
            raise Drop("missing_ward")
        closed = p["STATUS"] == "Resolved"
        reopened = p["REOPEN_STATUS"] == "Y" or p["SUBSTATUS"] == "Reopen"
        return self._finish({
            "ticket_id": f"mum-{p['COMPLAINTS_ID']}", "city": self.city, "data_quality": "real", "source": self.name,
            "category": "pothole", "text": p["COMPLAINT_TYPE"] or "Pothole", "lang": "other",
            "lat": round(lat, 6), "lng": round(lng, 6), "h3": cell, "ward": p["WARD_NAME"],
            "created_at": created, "closed_at": _iso(p["RESOLVED_DATE"]) if (closed or reopened) else None,
            "closed_by_hash": p["RESOLVED_BY"] or None,
            "status": "reopened" if reopened else ("closed" if closed else "open"),
            "closure_note": None, "closure_photo_url": None,
            "complaint_type": p["COMPLAINT_TYPE"], "zone": p["ZONE"] or None, "channel": p["COMPLAINT_SOURCE"] if "COMPLAINT_SOURCE" in p else None,
            "escalated": {"YES": True, "NO": False}.get(p["ESCALATED"]),
            "closing_basis": "pothole_resolved_date" if closed else None,
            "has_attended_image": (p["CONFIRM_POSTWORK_IMAGE"] == "Yes") if closed else None,
            "citizen_image_only": None, "from_pothole_layer": True,
        })
