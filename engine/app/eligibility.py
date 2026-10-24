"""Which checks can honestly apply to a ticket. The satellite rules come from data/README.md and backend_soham.md.

Sentinel-2 is 10 m per pixel: potholes and streetlights are invisible, large dump sites and drain corridors can show.
A check also needs a real point: ward-level tickets (Bengaluru) cannot be checked from orbit.
"""
SATELLITE_CATEGORIES = {"garbage", "drain"}
POINT_PRECISIONS = {"exact", "generated"}


def satellite_eligibility(category: str, location_precision: str | None) -> tuple[bool, str]:
    if location_precision not in POINT_PRECISIONS:
        return False, "no exact location for this ticket (ward-level only), so no satellite window"
    if category not in SATELLITE_CATEGORIES:
        return False, f"{category} is below Sentinel-2 10 m resolution; skipped"
    return True, "eligible"


def eligible_checks(category: str, location_precision: str | None) -> list[str]:
    checks = ["photo", "citizen", "human"]
    if satellite_eligibility(category, location_precision)[0]:
        checks.insert(1, "satellite")
    return checks
