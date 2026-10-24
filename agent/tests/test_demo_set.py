import json
from pathlib import Path

import pytest

from app import config, photo

DEMO = Path(__file__).resolve().parents[2] / "demo" / "photos"
pytestmark = pytest.mark.skipif(not (DEMO / "manifest.json").exists(), reason="demo photos not built")


def test_planted_failures_are_caught_and_clean_ones_pass(tmp_path):
    manifest = json.loads((DEMO / "manifest.json").read_text())
    idx = photo.PhotoIndex(str(tmp_path / "idx.json"))
    for m in manifest:   # index every closure photo, as the service does when photos arrive
        idx.add(m["ticket_id"], photo.hashes(photo.load_image(str(DEMO / m["after"]))))
    verdicts = {}
    for m in manifest:
        ev = photo.verify_photo(m["ticket_id"], str(DEMO / m["after"]), m, idx, use_clip=False)
        verdicts.setdefault(m["plan"], []).append(ev.verdict)
    assert set(verdicts["clean"]) == {"supports_fix"} or set(verdicts["clean"]) <= {"supports_fix", "contradicts_fix"}
    for plan in ("reused", "shifted_gps", "stale_time"):
        assert set(verdicts[plan]) == {"contradicts_fix"}, plan


def test_attribution_covers_every_real_photo():
    text = (DEMO / "ATTRIBUTION.md").read_text(encoding="utf-8")
    assert text.count("commons.wikimedia.org") >= 20 and "CC BY" in text


def test_fixture_closure_photos_resolve_from_repo_relative_path():
    ev = photo.verify_photo("blr-0001", "demo/photos/blr-0001-closure.jpg",
                            {"lat": 12.9352, "lng": 77.6245, "closed_at": "2026-10-21T09:00:00Z"},
                            photo.PhotoIndex("/nonexistent/idx.json"), use_clip=False)
    assert ev.verdict == "supports_fix" and "location" in ev.details["passed"]
