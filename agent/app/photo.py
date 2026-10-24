"""Module 1: photo verifier v1 (imagehash + EXIF). CLIP checks plug into verify_photo later.

Checks and hand-set likelihood ratios (to be calibrated on the shared benchmark):
  reused / near-duplicate photo on another ticket   LR ~ 8
  EXIF GPS far from the ticket location             LR ~ 4
  EXIF timestamp long before closed_at              LR ~ 3
  all available checks pass                         LR ~ 0.5
  nothing checkable (no EXIF, no duplicate)         LR 1.0, inconclusive
"""
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import httpx
import imagehash
from PIL import Image

from . import config
from .models import Evidence

DUP_HAMMING = 6            # pHash distance at or below this counts as near-duplicate
GPS_FAR_METRES = 300.0
STALE_DAYS = 30
LR_DUPLICATE, LR_GPS_FAR, LR_STALE, LR_CLEAN = 8.0, 4.0, 3.0, 0.5

_GPS_IFD = 0x8825
_EXIF_IFD = 0x8769
_DATETIME_ORIGINAL = 0x9003


def load_image(ref: str) -> Image.Image:
    if ref.startswith(("http://", "https://")):
        r = httpx.get(ref, timeout=10, follow_redirects=True)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content))
    path = Path(ref.removeprefix("file://"))
    if not path.is_absolute() and not path.exists():   # Engine fixtures use repo-relative paths (demo/photos/...)
        path = config.REPO_ROOT / path
    return Image.open(path)


def _to_deg(value) -> float:
    d, m, s = (float(x) for x in value)
    return d + m / 60 + s / 3600


def exif_info(img: Image.Image) -> dict:
    """Return {'lat','lng','taken_at'} with None for anything missing."""
    out = {"lat": None, "lng": None, "taken_at": None}
    try:
        exif = img.getexif()
        gps = exif.get_ifd(_GPS_IFD)
        if gps and all(k in gps for k in (1, 2, 3, 4)):
            lat, lng = _to_deg(gps[2]), _to_deg(gps[4])
            out["lat"] = -lat if gps[1] == "S" else lat
            out["lng"] = -lng if gps[3] == "W" else lng
        raw = exif.get_ifd(_EXIF_IFD).get(_DATETIME_ORIGINAL) or exif.get(0x0132)
        if raw:
            out["taken_at"] = datetime.strptime(raw, "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return out


def haversine_m(lat1, lng1, lat2, lng2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def hashes(img: Image.Image) -> dict:
    return {"phash": str(imagehash.phash(img)), "dhash": str(imagehash.dhash(img))}


class PhotoIndex:
    """ticket_id -> hashes for every prior closure photo. Brute force is fine at a few thousand photos."""

    def __init__(self, path: str | None = None):
        self.path = Path(path or config.PHOTO_INDEX_PATH)
        self.data: dict[str, dict] = {}
        if self.path.exists():
            self.data = json.loads(self.path.read_text())

    def nearest_other(self, ticket_id: str, phash_hex: str) -> tuple[str | None, int | None]:
        h = imagehash.hex_to_hash(phash_hex)
        best, best_d = None, None
        for tid, rec in self.data.items():
            if tid == ticket_id:
                continue
            d = h - imagehash.hex_to_hash(rec["phash"])
            if best_d is None or d < best_d:
                best, best_d = tid, int(d)
        return best, best_d

    def add(self, ticket_id: str, h: dict) -> None:
        self.data[ticket_id] = h
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data))


def verify_photo(ticket_id: str, closure_photo: str, ticket: dict | None = None,
                 index: PhotoIndex | None = None, cost: int = 1, use_clip: bool | None = None,
                 complaint_photo: str | None = None, embedder=None, use_dino: bool | None = None,
                 dino_embedder=None, use_vision: bool | None = None, vision_judge=None) -> Evidence:
    """ticket may carry lat, lng, closed_at (ISO). Missing fields skip the matching check."""
    ticket = ticket or {}
    index = index if index is not None else PhotoIndex()
    img = load_image(closure_photo)
    h = hashes(img)
    flags: list[str] = []
    passed: list[str] = []
    details: dict = {"phash": h["phash"], "checks": {}}

    # 1. reused photo
    other, dist = index.nearest_other(ticket_id, h["phash"])
    details["checks"]["duplicate"] = {"nearest_ticket": other, "hamming": dist}
    if dist is not None and dist <= DUP_HAMMING:
        flags.append("duplicate")
    elif dist is not None:
        passed.append("duplicate")

    # 2. EXIF location and time
    info = exif_info(img)
    if info["lat"] is not None and ticket.get("lat") is not None:
        metres = haversine_m(info["lat"], info["lng"], ticket["lat"], ticket["lng"])
        details["checks"]["location"] = {"distance_m": round(metres, 1)}
        (flags if metres > GPS_FAR_METRES else passed).append("location")
    if info["taken_at"] is not None and ticket.get("closed_at"):
        closed = datetime.fromisoformat(ticket["closed_at"].replace("Z", "+00:00"))
        age_days = (closed - info["taken_at"]).total_seconds() / 86400
        details["checks"]["timestamp"] = {"days_before_closure": round(age_days, 1)}
        (flags if age_days > STALE_DAYS else passed).append("timestamp")

    # 3. CLIP: does the closure photo still show the problem, and is it the same place as the complaint photo
    if (config.USE_CLIP if use_clip is None else use_clip) and ticket.get("category"):
        try:
            from . import clip_check
            before = complaint_photo or ticket.get("complaint_photo_url")
            cf, cp, cd = clip_check.clip_checks(img, ticket["category"],
                                                load_image(before) if before else None, embedder)
            flags += cf
            passed += cp
            details["checks"].update(cd)
        except Exception as exc:   # model missing or unreadable photo: keep v1 checks, say so
            details["clip_error"] = type(exc).__name__

    if (config.USE_VISION_LLM if use_vision is None else use_vision) and ticket.get("category"):
        try:
            from . import vision_check
            before = complaint_photo or ticket.get("complaint_photo_url")
            kw = {"judge_fn": vision_judge} if vision_judge else {}
            vf, vp, vd = vision_check.vision_checks(img, ticket["category"], load_image(before) if before else None, **kw)
            flags += [f for f in vf if f not in flags]
            passed += [p_ for p_ in vp if p_ not in passed and p_ not in flags]
            details["checks"].update(vd)
        except Exception as exc:
            details["vision_error"] = type(exc).__name__

    if config.USE_DINO if use_dino is None else use_dino:
        try:
            from . import dino_check
            before = complaint_photo or ticket.get("complaint_photo_url")
            df, dp, dd = dino_check.dino_checks(img, load_image(before) if before else None, dino_embedder)
            flags += df
            passed += dp
            details["checks"].update(dd)
        except Exception as exc:
            details["dino_error"] = type(exc).__name__

    lr_for = {"duplicate": LR_DUPLICATE, "location": LR_GPS_FAR, "timestamp": LR_STALE,
              "scene": 5.0, "before_after": 3.0, "same_scene": 3.0}
    if flags:
        lr = math.prod(lr_for[f] for f in flags)
        verdict, conf = "contradicts_fix", 0.9 if "duplicate" in flags else 0.7
    elif passed:
        lr, verdict, conf = LR_CLEAN, "supports_fix", 0.6
    else:
        lr, verdict, conf = 1.0, "inconclusive", 0.2
    details["flags"], details["passed"] = flags, passed
    index.add(ticket_id, h)   # remember this closure photo so later tickets can be compared against it
    return Evidence(ticket_id=ticket_id, check="photo", verdict=verdict, likelihood_ratio=lr,
                    confidence=conf, cost=cost, details=details)
