import csv
import json

import pandas as pd
import pytest

from app.connectors.base import CONTRACT_FIELDS
from app.connectors.mumbai import MumbaiSource, category
from app.ingest import ingest

C_FIELDS = ["COMPLAINT_ID", "COMPLAINT_SOURCE", "COMPLAINT_TYPE", "COMPLAINT_NAME", "COMPLAINT_SUBTYPE",
            "COMPLAINT_REG_LATITUDE", "COMPLAINT_REG_LONGITUDE", "COMPLAINT_REG_WARD", "COMPLAINT_ZONE",
            "COMPLAINT_STATUS", "COMP_REG_DATE", "REOPEN", "ESCALATED_NEW", "ESCALATED_REOPEN",
            "BEFORE_IMAGE_CITIZEN", "AFTER_IMAGE", "AFTER_IMAGE_DATE", "RESOLVED_DATE", "ATTENDED", "L1_REMARKS",
            "CURRENT_ESC_LVL", "INVALID", "GROUND_STAFF", "CO_EMP_ID"]
P_FIELDS = ["COMPLAINTS_ID", "COMPLAINT_TYPE", "COMPLAINTS_CREATION_DATE", "LATITUDE", "LONGITUDE", "WARD_NAME", "ZONE",
            "STATUS", "SUBSTATUS", "RESOLVED_DATE", "RESOLUTION_HRS", "FEEDBACK_STATUS", "COMPLAINT_RESOLUTION_TIME",
            "REOPEN_STATUS", "REOPEN_REMARKS", "VALID_IMAGE", "CONFIRM_IMAGE", "CONFIRM_POSTWORK_IMAGE", "ROAD_TYPE",
            "ESCALATED", "RELATED_COMP_ID", "RESOLVED_BY"]


def c(**kw):
    base = dict.fromkeys(C_FIELDS, "")
    base.update(COMPLAINT_ID="C1", COMPLAINT_SOURCE="1916", COMPLAINT_TYPE="Roads and traffic",
                COMPLAINT_NAME="Bad patches/potholes on roads", COMPLAINT_REG_LATITUDE="19.05",
                COMPLAINT_REG_LONGITUDE="72.85", COMPLAINT_REG_WARD="HW", COMPLAINT_ZONE="III",
                COMPLAINT_STATUS="CLOSED", COMP_REG_DATE="2026-04-01T10:00:00+00:00",
                AFTER_IMAGE="Initial Image By Citizen.jpg,Attended Image By L0(1).jpg",
                AFTER_IMAGE_DATE="2026-04-03T10:00:00+00:00", INVALID="NO", ESCALATED_NEW="NO", GROUND_STAFF="ab12cd34")
    base.update(kw)
    return base


def p(**kw):
    base = dict.fromkeys(P_FIELDS, "")
    base.update(COMPLAINTS_ID="C1", COMPLAINT_TYPE="Pothole", COMPLAINTS_CREATION_DATE="2026-04-01T10:00:00+00:00",
                LATITUDE="19.05", LONGITUDE="72.85", WARD_NAME="HW", ZONE="III", STATUS="Resolved", SUBSTATUS="NA",
                RESOLVED_DATE="2026-04-02T10:00:00+00:00", ESCALATED="N")
    base.update(kw)
    return base


def make(tmp_path, complaints, potholes=()):
    for name, fields, rows in (("mumbai_marg_complaints.csv", C_FIELDS, complaints),
                               ("mumbai_marg_potholes.csv", P_FIELDS, potholes)):
        with (tmp_path / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
    src = MumbaiSource(tmp_path)
    return src, {t["ticket_id"]: t for t in src.tickets()}


def test_closed_ticket_with_attended_image(tmp_path):
    src, t = make(tmp_path, [c()])
    x = t["mum-C1"]
    assert x["status"] == "closed" and x["category"] == "pothole" and x["data_quality"] == "real"
    assert x["has_attended_image"] is True and x["citizen_image_only"] is False
    assert x["closing_basis"] == "after_image_date" and x["res_hours"] == 48.0
    assert x["closed_at"] == "2026-04-03T10:00:00Z" and x["h3"]


def test_citizen_only_image_is_flagged(tmp_path):
    _, t = make(tmp_path, [c(AFTER_IMAGE="Initial Image By Citizen.jpg")])
    assert t["mum-C1"]["citizen_image_only"] is True and t["mum-C1"]["has_attended_image"] is False


@pytest.mark.parametrize("kw,reason", [
    (dict(COMPLAINT_STATUS="DISCARDED"), "discarded_status"),
    (dict(INVALID="YES"), "invalid_complaint"),
    (dict(COMPLAINT_REG_LATITUDE="19.07766361", COMPLAINT_REG_LONGITUDE="72.87740978"), "placeholder_location"),
    (dict(COMPLAINT_REG_LATITUDE="28.6", COMPLAINT_REG_LONGITUDE="77.2"), "outside_mumbai"),
    (dict(AFTER_IMAGE_DATE="2026-03-30T10:00:00+00:00"), "closed_before_created"),
    (dict(AFTER_IMAGE_DATE=""), "closed_without_time"),
    (dict(COMPLAINT_REG_WARD=""), "missing_ward"),
    (dict(COMPLAINT_STATUS="SOMETHING NEW"), "unknown_status:SOMETHING NEW"),
])
def test_drop_rules(tmp_path, kw, reason):
    src, t = make(tmp_path, [c(**kw)])
    assert t == {} and src.report[f"dropped:{reason}"] == 1


def test_open_ticket_has_no_closing_time(tmp_path):
    _, t = make(tmp_path, [c(COMPLAINT_STATUS="IN PROGRESS", AFTER_IMAGE="", AFTER_IMAGE_DATE="")])
    x = t["mum-C1"]
    assert x["status"] == "open" and x["closed_at"] is None and x["res_hours"] is None and x["has_attended_image"] is None


def test_pothole_layer_enriches_without_duplicating(tmp_path):
    src, t = make(tmp_path, [c()], [p(RESOLVED_DATE="2026-04-02T12:00:00+00:00")])
    assert list(t) == ["mum-C1"]
    x = t["mum-C1"]
    assert x["closing_basis"] == "pothole_resolved_date" and x["closed_at"] == "2026-04-02T12:00:00Z"
    assert x["from_pothole_layer"] is True


def test_reopened_pothole_keeps_signal_even_when_not_resolved(tmp_path):
    _, t = make(tmp_path, [c(COMPLAINT_STATUS="IN PROGRESS", AFTER_IMAGE="", AFTER_IMAGE_DATE="")],
                [p(STATUS="In Progress", SUBSTATUS="Reopen", REOPEN_STATUS="Y")])
    x = t["mum-C1"]
    assert x["status"] == "reopened" and x["closed_at"] == "2026-04-02T10:00:00Z"


def test_pothole_only_rows_are_added_once_and_invalid_ones_dropped(tmp_path):
    src, t = make(tmp_path, [c()], [p(COMPLAINTS_ID="P9", CONFIRM_POSTWORK_IMAGE="Yes"),
                                    p(COMPLAINTS_ID="P8", SUBSTATUS="Invalid")])
    assert set(t) == {"mum-C1", "mum-P9"}
    assert t["mum-P9"]["category"] == "pothole" and t["mum-P9"]["has_attended_image"] is True
    assert src.report["dropped:invalid_complaint"] == 1


@pytest.mark.parametrize("type_,name,expected", [
    ("Maintenance", "Encrochment on BMC Land / Footpath / drains", "other"),
    ("Solid Waste Management", "Complaints related with street lights", "streetlight"),
    ("Water supply", "Leaks / burst water lines", "water_leak"),
    ("Solid Waste Management", "Drain / manholes  block or overflow", "drain"),
    ("Drainage", "Raise / broken / missing manhole cover", "drain"),
    ("Roads and traffic", "Repairs/re-surfacing of roads/footpaths", "pothole"),
    ("Solid Waste Management", "Garbage / silt / tree branches not lifted", "garbage"),
    ("Hawkers", "Nuisance of illegal Hawking", "other"),
])
def test_category_mapping(type_, name, expected):
    assert category(type_, name) == expected


def test_every_ticket_has_contract_fields_and_ingest_writes_parquet(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    make(raw, [c(COMPLAINT_ID="A"), c(COMPLAINT_ID="B", COMPLAINT_STATUS="DISCARDED")])
    src = MumbaiSource(raw)
    df = ingest(src, tmp_path / "wh")
    assert all(col in df.columns for col in CONTRACT_FIELDS) and len(df) == 1
    assert len(pd.read_parquet(tmp_path / "wh" / "tickets_mumbai.parquet")) == 1
    assert json.loads((tmp_path / "wh" / "tickets_mumbai.report.json").read_text())["dropped:discarded_status"] == 1
