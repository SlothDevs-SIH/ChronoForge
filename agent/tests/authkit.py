"""Helpers for tests that run with sign-in switched on: locally signed HS256 tokens and seeded user rows."""
import io
import time

import jwt
from PIL import Image

from app.db import get_conn
from app.models import now_iso

SECRET = "test-secret-test-secret-test-secret-123456"
AUD = "authenticated"


def make_token(sub: str, email: str = "", confirmed: bool = True, expires_in: int = 3600, aud: str = AUD,
               secret: str = SECRET, alg: str = "HS256") -> str:
    claims = {"sub": sub, "email": email or f"{sub}@example.test", "aud": aud, "exp": int(time.time()) + expires_in,
              "role": "authenticated", "user_metadata": {"email_verified": confirmed}}
    return jwt.encode(claims, secret, algorithm=alg)


def bearer(sub: str, **kw) -> dict:
    return {"Authorization": f"Bearer {make_token(sub, **kw)}"}


def seed_user(user_id: str, role: str = "citizen", status: str = "active", requested_role: str | None = None) -> None:
    get_conn().execute("INSERT OR REPLACE INTO app_users (user_id, email, role, status, requested_role, created_at, updated_at) "
                       "VALUES (?,?,?,?,?,?,?)", (user_id, f"{user_id}@example.test", role, status, requested_role, now_iso(), now_iso()))
    get_conn().commit()


def link(user_id: str, ticket_id: str) -> None:
    get_conn().execute("INSERT OR REPLACE INTO user_tickets (user_id, ticket_id, linked_by, created_at) VALUES (?,?,?,?)",
                       (user_id, ticket_id, "test", now_iso()))
    get_conn().commit()


def jpeg_bytes(size=(64, 48), gps: bool = True, color=(200, 30, 30)) -> bytes:
    """A small JPEG, by default carrying EXIF GPS (Pune-ish) and a capture time."""
    img = Image.new("RGB", size, color)
    exif = Image.Exif()
    if gps:
        exif[0x0132] = "2026:10:01 10:00:00"
        gps_ifd = exif.get_ifd(0x8825)
        gps_ifd[1], gps_ifd[2] = "N", (18.0, 31.0, 0.0)
        gps_ifd[3], gps_ifd[4] = "E", (73.0, 51.0, 0.0)
    out = io.BytesIO()
    img.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def png_bytes(size=(32, 32)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (10, 120, 10)).save(out, format="PNG")
    return out.getvalue()


def webp_bytes(size=(32, 32)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (10, 10, 120)).save(out, format="WEBP")
    return out.getvalue()
