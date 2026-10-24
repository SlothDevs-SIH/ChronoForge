"""Citizen and officer evidence photos.

A photo attached here is stored as evidence for HUMAN REVIEW only: it gets no likelihood ratio and never enters the
fusion. The caller names the ticket explicitly (no guessing, no auto-attach). Stored copies are re-encoded from pixels, so
EXIF (including GPS) does not survive; the original position and time are kept server-side only, for the existing
location check, and are never returned to a caller.
"""
import hashlib
import io
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageOps

from . import audit, config
from .auth import Principal, authenticated, authorize_ticket, valid_ticket_id
from .db import get_conn, lock
from .http_utils import api_error, rate_limit
from .models import now_iso
from .photo import exif_info, haversine_m
from .storage import LocalStorage, get_storage

router = APIRouter()

# magic bytes -> (content type, Pillow format, extension)
_SIGNATURES = (
    (lambda b: b.startswith(b"\xff\xd8\xff"), ("image/jpeg", "JPEG", "jpg")),
    (lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"), ("image/png", "PNG", "png")),
    (lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP", ("image/webp", "WEBP", "webp")),
)
_MAX_PIXELS = 50_000_000


def sniff(data: bytes) -> tuple[str, str, str] | None:
    for test, kind in _SIGNATURES:
        if test(data):
            return kind
    return None


def clean_copy(data: bytes, fmt: str) -> tuple[bytes, dict]:
    """Decode, apply the orientation, copy the pixels into a fresh image (so no metadata survives) and re-encode.
    Returns (bytes, original_exif_summary)."""
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > _MAX_PIXELS:
            raise ValueError("image is too large")
        img.load()
    except Exception:
        raise api_error(422, "unreadable_image", "That file could not be read as an image.")
    info = exif_info(img)
    summary = {"lat": info["lat"], "lng": info["lng"],
               "taken_at": info["taken_at"].isoformat() if info["taken_at"] else None}
    img = ImageOps.exif_transpose(img)
    if fmt == "JPEG":
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
    elif img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGBA")
    clean = Image.frombytes(img.mode, img.size, img.tobytes())
    out = io.BytesIO()
    clean.save(out, format=fmt, **({"quality": 90} if fmt in ("JPEG", "WEBP") else {}))
    return out.getvalue(), summary


def _location_check(ticket_id: str, summary: dict) -> dict:
    """The existing EXIF-versus-ticket distance, computed server-side. Recorded for review, never turned into a ratio."""
    from .verification import _ticket_info
    t = _ticket_info(ticket_id) or {}
    if summary["lat"] is None or t.get("lat") is None:
        return {"checked": False}
    metres = haversine_m(summary["lat"], summary["lng"], t["lat"], t["lng"])
    return {"checked": True, "distance_m": round(metres, 1), "far": metres > config.VC["photo"]["gps_far_metres"]}


async def _read_capped(file: UploadFile) -> bytes:
    buf = bytearray()
    while chunk := await file.read(1024 * 1024):
        buf += chunk
        if len(buf) > config.MAX_UPLOAD_BYTES:
            raise api_error(413, "file_too_large", f"Photos can be at most {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    return bytes(buf)


@router.post("/tickets/{ticket_id}/evidence/photo", tags=["evidence"], dependencies=[Depends(rate_limit("upload", 10, 60))])
async def upload_photo(ticket_id: str, file: UploadFile = File(...), idempotency_key: str | None = Header(default=None),
                       p: Principal = Depends(authenticated)):
    valid_ticket_id(ticket_id)
    authorize_ticket(p, ticket_id)
    data = await _read_capped(file)
    if not data:
        raise api_error(422, "empty_file", "The file is empty.")
    kind = sniff(data)
    if kind is None:
        raise api_error(415, "unsupported_media_type", "Only JPEG, PNG and WebP photos are accepted.")
    content_type, fmt, ext = kind
    uid = p.user_id or "unknown"
    if idempotency_key:
        row = get_conn().execute("SELECT * FROM idempotency_keys WHERE user_id=? AND idem_key=?", (uid, idempotency_key)).fetchone()
        if row:
            if row["ticket_id"] != ticket_id:
                raise api_error(409, "idempotency_conflict", "That Idempotency-Key was used for a different ticket.")
            return json.loads(row["response"])
    sha = hashlib.sha256(data).hexdigest()
    existing = get_conn().execute("SELECT evidence_id FROM evidence_uploads WHERE ticket_id=? AND sha256=?", (ticket_id, sha)).fetchone()
    if existing:
        resp = {"evidence_id": existing["evidence_id"], "sha256": sha, "duplicate": True}
    else:
        stored, summary = clean_copy(data, fmt)
        summary["location_check"] = _location_check(ticket_id, summary)
        evidence_id = str(uuid4())
        key = f"{ticket_id}/{evidence_id}.{ext}"
        try:
            get_storage().put(key, stored, content_type)
        except Exception as exc:
            if hasattr(exc, "status_code"):
                raise
            raise api_error(503, "storage_unavailable", "The photo could not be stored. Try again.")
        with lock():
            get_conn().execute("INSERT INTO evidence_uploads (evidence_id, ticket_id, user_id, sha256, content_type, size_bytes, "
                               "storage_key, exif_summary, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                               (evidence_id, ticket_id, uid, sha, content_type, len(stored), key, json.dumps(summary), now_iso()))
            get_conn().commit()
        audit.append("evidence_photo_uploaded", {"ticket_id": ticket_id, "evidence_id": evidence_id, "sha256": sha, "by": uid})
        resp = {"evidence_id": evidence_id, "sha256": sha, "duplicate": False}
    if idempotency_key:
        with lock():
            get_conn().execute("DELETE FROM idempotency_keys WHERE user_id=? AND idem_key=?", (uid, idempotency_key))
            get_conn().execute("INSERT INTO idempotency_keys (user_id, idem_key, ticket_id, response, created_at) VALUES (?,?,?,?,?)",
                               (uid, idempotency_key, ticket_id, json.dumps(resp), now_iso()))
            get_conn().commit()
    return resp


@router.get("/tickets/{ticket_id}/evidence", tags=["evidence"])
def list_photos(ticket_id: str, p: Principal = Depends(authenticated)):
    valid_ticket_id(ticket_id)
    authorize_ticket(p, ticket_id)
    rows = get_conn().execute("SELECT evidence_id, sha256, content_type, size_bytes, created_at FROM evidence_uploads "
                              "WHERE ticket_id=? ORDER BY created_at", (ticket_id,)).fetchall()
    return [{"evidence_id": r["evidence_id"], "sha256": r["sha256"], "content_type": r["content_type"],
             "size_bytes": r["size_bytes"], "created_at": r["created_at"]} for r in rows]


@router.get("/evidence/{evidence_id}/url", tags=["evidence"])
def photo_url(evidence_id: str, p: Principal = Depends(authenticated)):
    """A short-lived signed URL for one stored photo."""
    row = get_conn().execute("SELECT ticket_id, storage_key FROM evidence_uploads WHERE evidence_id=?", (evidence_id,)).fetchone()
    if row is None:
        raise api_error(404, "not_found", "No such photo.")
    authorize_ticket(p, row["ticket_id"])
    return {"url": get_storage().signed_url(row["storage_key"], config.SIGNED_URL_SECONDS),
            "expires_in": config.SIGNED_URL_SECONDS}


@router.get("/evidence/file/{token}", tags=["evidence"], include_in_schema=False)
def photo_file(token: str):
    """Serves a stored photo for the local backend, only with an unexpired signed token."""
    store = get_storage()
    if not isinstance(store, LocalStorage):
        raise api_error(404, "not_found", "Not served here.")
    key = store.key_from_token(token)
    try:
        data = store.read(key)
    except (FileNotFoundError, ValueError):
        raise api_error(404, "not_found", "No such photo.")
    ctype = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(key.rsplit(".", 1)[-1], "application/octet-stream")
    return Response(data, media_type=ctype, headers={"Cache-Control": "private, max-age=60", "X-Content-Type-Options": "nosniff"})
