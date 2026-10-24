import csv

import pytest

from app.connectors.bengaluru import BengaluruSource, category

HEAD = ["Complaint ID", "Category", "Sub Category", "Grievance Date", "Ward Name", "Grievance Status", "Staff Remarks", "Staff Name"]
MAP_HEAD = ["complaint_ward_name", "boundary_ward_name", "zone", "centroid_lat", "centroid_lng", "match"]


def row(**kw):
    base = {"Complaint ID": "1", "Category": "Electrical", "Sub Category": "Street Light Not Working",
            "Grievance Date": "2024-12-31 05:52:00.000000000", "Ward Name": "Jakkur", "Grievance Status": "Closed",
            "Staff Remarks": "Attended", "Staff Name": "Sachin Malagi/AE"}
    base.update(kw)
    return base


def make(tmp_path, rows):
    with (tmp_path / "bbmp_2024.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEAD)
        w.writeheader()
        w.writerows(rows)
    with (tmp_path / "map.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(MAP_HEAD)
        w.writerow(["Jakkur", "Jakkuru", "Yelahanka", "13.07", "77.61", "fuzzy"])
        w.writerow(["Someshwara", "", "", "", "", "unmapped"])
    src = BengaluruSource(tmp_path, tmp_path / "map.csv", years=range(2024, 2025))
    return src, {t["ticket_id"]: t for t in src.tickets()}


def test_closed_ticket_has_ward_centroid_and_no_closing_time(tmp_path):
    _, t = make(tmp_path, [row()])
    x = t["blr-1"]
    assert x["status"] == "closed" and x["data_quality"] == "partial" and x["category"] == "streetlight"
    assert x["closed_at"] is None and x["h3"] is None
    assert x["location_precision"] == "ward_centroid" and (x["lat"], x["lng"]) == (13.07, 77.61)
    assert x["ward_zone"] == "Yelahanka"


def test_created_time_is_converted_from_ist_to_utc(tmp_path):
    _, t = make(tmp_path, [row()])
    assert t["blr-1"]["created_at"] == "2024-12-31T00:22:00Z"


@pytest.mark.parametrize("raw,expected", [("Closed", "closed"), ("Resolved", "closed"), ("ReOpen", "reopened"),
                                          ("Registered", "open"), ("In Progress", "open"), ("Long Term Solution", "open")])
def test_status_mapping(tmp_path, raw, expected):
    _, t = make(tmp_path, [row(**{"Grievance Status": raw})])
    assert t["blr-1"]["status"] == expected


@pytest.mark.parametrize("raw,reason", [("Rejected", "status_rejected"), ("Non Relevant", "status_non_relevant"),
                                        ("null", "status_null")])
def test_dropped_statuses(tmp_path, raw, reason):
    src, t = make(tmp_path, [row(**{"Grievance Status": raw})])
    assert t == {} and src.report[f"dropped:{reason}"] == 1


def test_duplicate_ids_and_missing_ward_are_dropped(tmp_path):
    src, t = make(tmp_path, [row(), row(), row(**{"Complaint ID": "2", "Ward Name": ""})])
    assert list(t) == ["blr-1"]
    assert src.report["dropped:duplicate_id"] == 1 and src.report["dropped:missing_ward"] == 1


def test_unmapped_ward_keeps_ticket_without_location(tmp_path):
    _, t = make(tmp_path, [row(**{"Ward Name": "Someshwara"})])
    x = t["blr-1"]
    assert x["location_precision"] == "none" and x["lat"] is None and x["lng"] is None


def test_staff_is_hashed_and_role_kept(tmp_path):
    _, t = make(tmp_path, [row(), row(**{"Complaint ID": "2", "Staff Name": "Sachin Malagi/AE"})])
    assert t["blr-1"]["closed_by_hash"] == t["blr-2"]["closed_by_hash"]
    assert "Sachin" not in str(t["blr-1"].values()) and t["blr-1"]["staff_role"] == "AE"


def test_remark_signals_only_for_non_open(tmp_path):
    _, t = make(tmp_path, [row(**{"Staff Remarks": "."}), row(**{"Complaint ID": "2", "Staff Remarks": "Attended"}),
                           row(**{"Complaint ID": "3", "Grievance Status": "Registered", "Staff Remarks": "x"})])
    assert t["blr-1"]["remark_blank_like"] is True and t["blr-2"]["remark_blank_like"] is False
    assert t["blr-2"]["remark_norm"] == "attended"
    assert t["blr-3"]["remark_norm"] is None and t["blr-3"]["closure_note"] is None


@pytest.mark.parametrize("cat,sub,expected", [
    ("Electrical", "Street Light Not Working", "streetlight"),
    ("Electrical", "Requirement For New Street Lights", "other"),
    ("Road Maintenance(Engg)", "Potholes", "pothole"),
    ("Road Maintenance(Engg)", "Road side drains", "drain"),
    ("Road Maintenance(Engg)", "water stagnation", "drain"),
    ("Storm  Water Drain(SWD)", "Maintenance of SWD", "drain"),
    ("Solid Waste (Garbage) Related", "Garbage dump", "garbage"),
    ("Road Maintenance(Engg)", "Debris Removal / Construction Material", "garbage"),
    ("Health Dept", "Dengue positive", "other"),
])
def test_category_mapping(cat, sub, expected):
    assert category(cat, sub) == expected
