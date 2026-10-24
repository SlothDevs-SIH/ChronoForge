"""Download Mumbai (BMC MARG) complaint records from BMC's public ArcGIS MapServer into data/raw/.

Read-only queries. Deliberately NOT downloaded: citizen contact numbers, user ids, names, addresses,
landmarks and free-text descriptions. Staff ids are hashed here so raw files never hold them.
BMC states no explicit open-data licence for this service: use for the hackathon prototype with
attribution to BMC/MCGM, and check with BMC before any wider reuse.

Run from the repo root:  python data/scripts/download_mumbai.py
"""
import csv
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE = "https://marg.mcgm.gov.in/server/rest/services/MARG_APP/MARG_Application_Prod/MapServer"
OUT = Path(__file__).resolve().parents[1] / "raw"
PAGE = 2000

LAYERS = {
    "mumbai_marg_complaints": {
        "layer": 0,
        "fields": ["COMPLAINT_ID", "COMPLAINT_SOURCE", "COMPLAINT_TYPE", "COMPLAINT_NAME", "COMPLAINT_SUBTYPE",
                   "COMPLAINT_REG_LATITUDE", "COMPLAINT_REG_LONGITUDE", "COMPLAINT_REG_WARD", "COMPLAINT_ZONE",
                   "COMPLAINT_STATUS", "COMP_REG_DATE", "REOPEN", "ESCALATED_NEW", "ESCALATED_REOPEN",
                   "BEFORE_IMAGE_CITIZEN", "AFTER_IMAGE", "AFTER_IMAGE_DATE", "RESOLVED_DATE", "ATTENDED",
                   "L1_REMARKS", "CURRENT_ESC_LVL", "INVALID", "GROUND_STAFF", "CO_EMP_ID"],
        "dates": {"COMP_REG_DATE", "AFTER_IMAGE_DATE", "RESOLVED_DATE"},
        "hash": {"GROUND_STAFF", "CO_EMP_ID"},
    },
    "mumbai_marg_potholes": {
        "layer": 16,
        "fields": ["COMPLAINTS_ID", "COMPLAINT_TYPE", "COMPLAINTS_CREATION_DATE", "LATITUDE", "LONGITUDE",
                   "WARD_NAME", "ZONE", "STATUS", "SUBSTATUS", "RESOLVED_DATE", "RESOLUTION_HRS", "FEEDBACK_STATUS",
                   "COMPLAINT_RESOLUTION_TIME", "REOPEN_STATUS", "REOPEN_REMARKS", "VALID_IMAGE", "CONFIRM_IMAGE",
                   "CONFIRM_POSTWORK_IMAGE", "ROAD_TYPE", "ESCALATED", "RELATED_COMP_ID", "RESOLVED_BY"],
        "dates": {"COMPLAINTS_CREATION_DATE", "RESOLVED_DATE"},
        "hash": {"RESOLVED_BY"},
    },
}


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat() if isinstance(ms, (int, float)) else ""


def h(v):
    return hashlib.sha1(str(v).encode()).hexdigest()[:8] if v not in (None, "") else ""


def pull(name: str, spec: dict) -> int:
    url = f"{BASE}/{spec['layer']}/query"
    path = OUT / f"{name}.csv"
    n, offset = 0, 0
    with httpx.Client(timeout=90) as c, path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=spec["fields"])
        w.writeheader()
        while True:
            r = c.get(url, params={"where": "1=1", "outFields": ",".join(spec["fields"]), "returnGeometry": "false",
                                   "orderByFields": "OBJECTID", "resultOffset": offset, "resultRecordCount": PAGE, "f": "json"})
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                sys.exit(f"{name}: {data['error']}")
            rows = data.get("features", [])
            for f in rows:
                a = f["attributes"]
                w.writerow({k: iso(a.get(k)) if k in spec["dates"] else h(a.get(k)) if k in spec["hash"] else a.get(k)
                            for k in spec["fields"]})
            n += len(rows)
            print(f"{name}: {n} rows", end="\r")
            if not data.get("exceededTransferLimit") and len(rows) < PAGE:
                break
            offset += PAGE
    print(f"{name}: {n} rows -> {path}")
    return n


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, spec in LAYERS.items():
        pull(name, spec)
