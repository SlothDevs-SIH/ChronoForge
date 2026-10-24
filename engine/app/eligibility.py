"""Which checks can honestly apply to a ticket. The satellite rules come from data/README.md and backend_soham.md.

Sentinel-2 is 10 m per pixel (one pixel is 100 m2): potholes, streetlights, manhole covers and a single garbage pile are
invisible. Only large-footprint problems can show: dumping grounds, nullah and drain corridors,
waterlogging over hundreds of metres, encroachment on nullahs or large plots. A check also needs a real point: ward-level tickets
(Bengaluru) cannot be checked from orbit.

Tickets carry no size field, so scale is read from the complaint wording (Mumbai's `text` is the structured complaint
name, never citizen free text). A ticket is satellite-eligible only when its wording names a large-area problem; wording
that gives no sign of scale is "not applicable", never a guess.
"""
import re

SATELLITE_CATEGORIES = {"garbage", "drain", "other"}   # the category mapping is coarse, so the wording decides below
POINT_PRECISIONS = {"exact", "generated"}

# Complaint wording that names a problem spanning many 10 m pixels. Deliberately narrow: plain "garbage not lifted",
# "overflowing drain", "removal of debris", "manhole cover", footpath encroachment and "unauthorised construction / shed"
# are single-site or a few metres wide, so they are not here.
LARGE_AREA = re.compile(
    r"dumping|dump\s*(yard|site|ground)|landfill|nullah|nalla|culvert|waterlog|water[\s-]*log|flood|inundat"
    r"|encroachment\s+(of|on)\s+(land|plot)",
    re.IGNORECASE)

NOT_APPLICABLE_SMALL = ("not applicable: {what} is far smaller than one Sentinel-2 pixel (10 m x 10 m), so a satellite cannot "
                        "confirm it was fixed. Satellite checks cover large-area problems such as waterlogging over hundreds of "
                        "metres, dump sites, nullah corridors or large encroachment.")
NOT_APPLICABLE_NO_SCALE = ("not applicable: nothing in this ticket says the problem covers a large area, and a single garbage pile "
                           "or small defect is below Sentinel-2's 10 m pixel. Satellite checks cover large-area problems only.")


def is_large_area(text: str | None) -> bool:
    return bool(text) and LARGE_AREA.search(text) is not None


def satellite_eligibility(category: str, location_precision: str | None, text: str | None = None) -> tuple[bool, str]:
    if location_precision not in POINT_PRECISIONS:
        return False, "no exact location for this ticket (ward-level only), so no satellite window"
    if category not in SATELLITE_CATEGORIES:
        return False, NOT_APPLICABLE_SMALL.format(what=category.replace("_", " "))
    if not is_large_area(text):
        return False, NOT_APPLICABLE_NO_SCALE
    return True, "eligible: large-area problem"


def eligible_checks(category: str, location_precision: str | None, text: str | None = None) -> list[str]:
    checks = ["photo", "citizen", "human"]
    if satellite_eligibility(category, location_precision, text)[0]:
        checks.insert(1, "satellite")
    return checks
