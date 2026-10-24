"""Accounts, roles and signed session tokens (stdlib only). Roles live in the users table, never in client data.

citizen: self-registers, active at once.  officer: self-registers as pending, an admin approves.  admin: seeded from env.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException

from . import config
from .db import get_conn, lock

ROLES = ("citizen", "officer", "admin")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_runtime_secret = secrets.token_bytes(32)


def _secret() -> bytes:
    return config.AUTH_SECRET.encode() if config.AUTH_SECRET else _runtime_secret


def _hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return f"{salt.hex()}${digest.hex()}"


def _check(password: str, stored: str) -> bool:
    salt, digest = stored.split("$")
    return hmac.compare_digest(_hash(password, bytes.fromhex(salt)).split("$")[1], digest)


def _public(row) -> dict:
    return {"user_id": row["user_id"], "email": row["email"], "name": row["name"], "role": row["role"], "status": row["status"]}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def register(email: str, name: str, password: str, role: str) -> dict:
    email = email.strip().lower()
    if not _EMAIL.match(email):
        raise ValueError("enter a valid email address")
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    if not name.strip():
        raise ValueError("name is required")
    if role not in ("citizen", "officer"):
        raise ValueError("only citizen and officer accounts can be requested")
    status = "active" if role == "citizen" else "pending"
    with lock():
        conn = get_conn()
        if conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise ValueError("an account with this email already exists")
        uid = "u_" + uuid.uuid4().hex[:12]
        conn.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?)", (uid, email, name.strip(), _hash(password), role, status, _now()))
        conn.commit()
        return _public(conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone())


def login(email: str, password: str) -> dict:
    row = get_conn().execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
    if row is None or not _check(password, row["pw_hash"]):
        raise PermissionError("incorrect email or password")
    if row["status"] == "disabled":
        raise PermissionError("this account is disabled")
    return {"token": make_token(row["user_id"]), "user": _public(row)}


def make_token(user_id: str) -> str:
    claims = {"sub": user_id, "exp": int(time.time()) + config.AUTH_TOKEN_HOURS * 3600}
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode()
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def user_from_token(token: str):
    try:
        body, sig = token.split(".")
        if not hmac.compare_digest(hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest(), sig):
            return None
        claims = json.loads(base64.urlsafe_b64decode(body))
        if claims["exp"] < time.time():
            return None
    except Exception:
        return None
    row = get_conn().execute("SELECT * FROM users WHERE user_id=?", (claims["sub"],)).fetchone()
    return row if row and row["status"] != "disabled" else None


def seed_admin() -> None:
    """Create the first admin from env, once. Existing admins are never touched."""
    if not (config.FIRST_ADMIN_EMAIL and config.FIRST_ADMIN_PASSWORD):
        return
    with lock():
        conn = get_conn()
        if conn.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
            return
        conn.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?)", ("u_" + uuid.uuid4().hex[:12], config.FIRST_ADMIN_EMAIL.strip().lower(),
                     "Administrator", _hash(config.FIRST_ADMIN_PASSWORD), "admin", "active", _now()))
        conn.commit()


def list_users() -> list[dict]:
    return [_public(r) for r in get_conn().execute("SELECT * FROM users ORDER BY created_at")]


def set_status(user_id: str, status: str) -> dict:
    with lock():
        conn = get_conn()
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            raise KeyError(user_id)
        if row["role"] == "admin":
            raise ValueError("admin accounts cannot be changed here")
        conn.execute("UPDATE users SET status=? WHERE user_id=?", (status, user_id))
        conn.commit()
        return _public(conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone())


def my_tickets(user_id: str) -> list[str]:
    rows = get_conn().execute("SELECT ticket_id FROM user_tickets WHERE user_id=? ORDER BY added_at", (user_id,))
    return [r["ticket_id"] for r in rows]


def add_ticket(user_id: str, ticket_id: str) -> None:
    ticket_id = ticket_id.strip()
    if not ticket_id or len(ticket_id) > 80:
        raise ValueError("enter the ticket id from your complaint receipt")
    with lock():
        get_conn().execute("INSERT OR IGNORE INTO user_tickets VALUES (?,?,?)", (user_id, ticket_id, _now()))
        get_conn().commit()


def current_user(authorization: str | None = Header(default=None), x_admin_token: str | None = Header(default=None)):
    """The signed-in user, or None. The legacy admin-token header counts as an admin."""
    if config.ADMIN_TOKEN and x_admin_token and hmac.compare_digest(x_admin_token, config.ADMIN_TOKEN):
        return {"user_id": "token", "email": "", "name": "admin token", "role": "admin", "status": "active"}
    if authorization and authorization.lower().startswith("bearer "):
        row = user_from_token(authorization[7:].strip())
        if row is not None:
            return _public(row)
    return None


def require_role(*roles: str):
    """Dependency: signed-in, active, and one of `roles`. Off entirely when AGENT_AUTH_ENFORCE=0."""
    def dep(user=Depends(current_user)):
        if not config.AUTH_ENFORCE:
            return user
        if user is None:
            raise HTTPException(401, "sign in required")
        if user["status"] != "active":
            raise HTTPException(403, "your account is waiting for approval")
        if user["role"] not in roles:
            raise HTTPException(403, "your role cannot do this")
        return user
    return dep
