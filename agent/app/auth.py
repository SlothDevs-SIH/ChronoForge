"""Sign-in and roles (contract/AUTH_AND_DEPLOY.md).

The browser signs in with Supabase and sends `Authorization: Bearer <access token>`. This module verifies the token
(HS256 with SUPABASE_JWT_SECRET, or the project's public keys from JWKS) and loads the caller's role from the
`app_users` table. Roles are never read from client-editable token metadata.

AUTH_REQUIRED=0 (the default) keeps the local demo open: every request is a local admin. Production sets AUTH_REQUIRED=1.
"""
import re
import threading
from dataclasses import dataclass, field
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel

from . import audit, config
from .db import get_conn, lock
from .http_utils import api_error, note_user, rate_limit
from .models import now_iso

Role = Literal["citizen", "officer", "admin"]
STAFF = ("officer", "admin")
_TICKET_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,80}$")


@dataclass
class Principal:
    user_id: str | None = None
    email: str | None = None
    role: str | None = None
    status: str | None = None
    requested_role: str | None = None
    ticket_ids: list[str] = field(default_factory=list)
    anonymous: bool = False
    local: bool = False

    @property
    def active(self) -> bool:
        return self.status == "active"

    @property
    def staff(self) -> bool:
        return self.active and self.role in STAFF


LOCAL = Principal(user_id="local", email="local@localhost", role="admin", status="active", local=True)
ANON = Principal(anonymous=True)


# ---- token verification -------------------------------------------------------------------------------------------
_jwks_lock = threading.Lock()
_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def _jwks_client() -> jwt.PyJWKClient:
    url = f"{config.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
    with _jwks_lock:
        if url not in _jwks_clients:
            _jwks_clients[url] = jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)
        return _jwks_clients[url]


def decode_token(token: str) -> dict:
    """Verify signature, expiry and audience. Raises a 401 (bad token) or 503 (auth not configured)."""
    try:
        alg = jwt.get_unverified_header(token).get("alg", "")
    except jwt.PyJWTError:
        raise api_error(401, "invalid_token", "The sign-in token is not valid.", {"WWW-Authenticate": "Bearer"})
    opts = {"require": ["exp", "sub"]}
    try:
        if alg == "HS256":
            if not config.SUPABASE_JWT_SECRET:
                raise api_error(503, "auth_not_configured", "Sign-in is not configured on the server.")
            return jwt.decode(token, config.SUPABASE_JWT_SECRET, algorithms=["HS256"],
                              audience=config.SUPABASE_JWT_AUDIENCE, options=opts)
        if alg in ("ES256", "RS256"):
            if not config.SUPABASE_URL:
                raise api_error(503, "auth_not_configured", "Sign-in is not configured on the server.")
            key = _jwks_client().get_signing_key_from_jwt(token).key
            return jwt.decode(token, key, algorithms=[alg], audience=config.SUPABASE_JWT_AUDIENCE, options=opts)
    except jwt.ExpiredSignatureError:
        raise api_error(401, "token_expired", "Your session has expired. Sign in again.", {"WWW-Authenticate": "Bearer"})
    except jwt.PyJWTError:
        raise api_error(401, "invalid_token", "The sign-in token is not valid.", {"WWW-Authenticate": "Bearer"})
    raise api_error(401, "invalid_token", "The sign-in token is not valid.", {"WWW-Authenticate": "Bearer"})


def _email_confirmed(claims: dict) -> bool:
    meta = claims.get("user_metadata") or {}
    return claims.get("email_verified") is True or meta.get("email_verified") is True


# ---- profiles -----------------------------------------------------------------------------------------------------
def _tickets_of(user_id: str) -> list[str]:
    rows = get_conn().execute("SELECT ticket_id FROM user_tickets WHERE user_id=? ORDER BY ticket_id", (user_id,)).fetchall()
    return [r["ticket_id"] for r in rows]


def _principal_from_row(r) -> Principal:
    return Principal(user_id=r["user_id"], email=r["email"], role=r["role"], status=r["status"],
                     requested_role=r["requested_role"], ticket_ids=_tickets_of(r["user_id"]))


def load_principal(claims: dict) -> Principal:
    """Get or create the caller's profile. A confirmed email in ADMIN_EMAILS is made an active admin."""
    user_id, email = claims["sub"], (claims.get("email") or "").lower()
    is_admin_email = bool(email) and email in config.ADMIN_EMAILS and _email_confirmed(claims)
    with lock():
        c = get_conn()
        row = c.execute("SELECT * FROM app_users WHERE user_id=?", (user_id,)).fetchone()
        now = now_iso()
        if row is None:
            role, status = ("admin", "active") if is_admin_email else ("citizen", "active")
            c.execute("INSERT INTO app_users (user_id, email, role, status, requested_role, created_at, updated_at) "
                      "VALUES (?,?,?,?,?,?,?)", (user_id, email, role, status, None, now, now))
            c.commit()
            audit.append("user_created", {"user_id": user_id, "role": role, "status": status})
        elif is_admin_email and not (row["role"] == "admin" and row["status"] == "active"):
            c.execute("UPDATE app_users SET role='admin', status='active', updated_at=?, decided_by='ADMIN_EMAILS' "
                      "WHERE user_id=?", (now, user_id))
            c.commit()
            audit.append("user_promoted", {"user_id": user_id, "by": "ADMIN_EMAILS"})
        row = c.execute("SELECT * FROM app_users WHERE user_id=?", (user_id,)).fetchone()
        return _principal_from_row(row)


def _bearer(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    scheme, _, token = h.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


# ---- dependencies -------------------------------------------------------------------------------------------------
def principal(request: Request) -> Principal:
    """Whoever is calling. Anonymous (no token) is allowed here; a token that is present must be valid."""
    if not config.AUTH_REQUIRED:
        return LOCAL
    token = _bearer(request)
    if token is None:
        return ANON
    p = load_principal(decode_token(token))
    note_user(p.user_id)
    return p


def authenticated(p: Principal = Depends(principal)) -> Principal:
    """A signed-in caller of any status (pending and rejected users may still read their own profile)."""
    if p.anonymous:
        raise api_error(401, "unauthorized", "Sign in to continue.", {"WWW-Authenticate": "Bearer"})
    return p


def require_active(p: Principal = Depends(authenticated)) -> Principal:
    if not p.active:
        raise api_error(403, "account_not_active", "Your account is waiting for approval." if p.status == "pending"
                        else "Your account does not have access.")
    return p


def require_staff(p: Principal = Depends(authenticated)) -> Principal:
    if not p.staff:
        raise api_error(403, "forbidden", "This needs an approved officer or admin account.")
    return p


def require_admin(p: Principal = Depends(authenticated)) -> Principal:
    if not (p.active and p.role == "admin"):
        raise api_error(403, "forbidden", "This needs an admin account.")
    return p


def staff_or_admin_token(p: Principal = Depends(principal), x_admin_token: str | None = Header(default=None)) -> Principal:
    """Endpoints that message people or read local files. The shared admin token still works (existing scripts);
    otherwise an approved officer or admin. With AUTH_REQUIRED=0 the legacy rule applies: open unless a token is set."""
    if config.ADMIN_TOKEN and x_admin_token == config.ADMIN_TOKEN:
        return p if not p.anonymous else Principal(user_id="admin-token", role="admin", status="active", local=True)
    if not config.AUTH_REQUIRED:
        if config.ADMIN_TOKEN:
            raise api_error(403, "forbidden", "admin token required")
        return p
    if p.anonymous:
        raise api_error(401, "unauthorized", "Sign in to continue.", {"WWW-Authenticate": "Bearer"})
    if not p.staff:
        raise api_error(403, "forbidden", "This needs an approved officer or admin account.")
    return p


def staff_human(p: Principal = Depends(principal), x_admin_token: str | None = Header(default=None)) -> Principal:
    """For decisions: a person is always on record. The admin token is only accepted in local (AUTH_REQUIRED=0) runs."""
    if not config.AUTH_REQUIRED:
        if config.ADMIN_TOKEN and x_admin_token != config.ADMIN_TOKEN:
            raise api_error(403, "forbidden", "admin token required")
        return p
    if p.anonymous:
        raise api_error(401, "unauthorized", "Sign in to continue.", {"WWW-Authenticate": "Bearer"})
    if not p.staff:
        raise api_error(403, "forbidden", "This needs an approved officer or admin account.")
    return p


def authorize_ticket(p: Principal, ticket_id: str, *, public_demo: bool = False, citizen_ok: bool = True) -> None:
    """Staff may see any ticket. An active citizen sees only tickets linked to them. Anonymous callers get a demo ticket
    only when PUBLIC_DEMO_RUNS=1 and the endpoint allows it."""
    if public_demo and config.PUBLIC_DEMO_RUNS and ticket_id.startswith("DEMO-"):
        return
    if p.anonymous:
        raise api_error(401, "unauthorized", "Sign in to continue.", {"WWW-Authenticate": "Bearer"})
    if not p.active:
        raise api_error(403, "account_not_active", "Your account does not have access.")
    if p.staff or p.local:
        return
    if citizen_ok and p.role == "citizen" and ticket_id in p.ticket_ids:
        return
    raise api_error(403, "forbidden", "You do not have access to this ticket.")


def valid_ticket_id(ticket_id: str) -> str:
    if not _TICKET_ID.match(ticket_id):
        raise api_error(422, "validation_error", "ticket_id has invalid characters")
    return ticket_id


# ---- endpoints ----------------------------------------------------------------------------------------------------
router = APIRouter()


class Profile(BaseModel):
    user_id: str
    email: str
    role: Role
    status: Literal["active", "pending", "rejected"]
    requested_role: str | None = None
    ticket_ids: list[str] = []


def _profile(p: Principal) -> Profile:
    return Profile(user_id=p.user_id or "", email=p.email or "", role=p.role or "citizen", status=p.status or "active",
                   requested_role=p.requested_role, ticket_ids=p.ticket_ids)


@router.get("/auth/me", response_model=Profile, tags=["auth"])
def me(p: Principal = Depends(authenticated)):
    """Who am I and what may I do. Creates the profile on first call."""
    return _profile(p)


class ProfileRequest(BaseModel):
    requested_role: Literal["citizen", "officer"]


@router.post("/auth/profile", response_model=Profile, tags=["auth"],
             dependencies=[Depends(rate_limit("auth_profile", 10, 60))])
def set_profile(req: ProfileRequest, p: Principal = Depends(require_active)):
    """Officer sign-up: asks for officer access, which stays `pending` until an admin approves. Cannot be used to change
    an active officer or admin."""
    if p.local:
        return _profile(p)
    if p.active and p.role in STAFF:
        raise api_error(409, "already_privileged", "This account already has a staff role.")
    role, status = ("officer", "pending") if req.requested_role == "officer" else ("citizen", "active")
    with lock():
        get_conn().execute("UPDATE app_users SET role=?, status=?, requested_role=?, updated_at=? WHERE user_id=?",
                           (role, status, req.requested_role, now_iso(), p.user_id))
        get_conn().commit()
    audit.append("profile_requested", {"user_id": p.user_id, "requested_role": req.requested_role})
    return _profile(load_principal({"sub": p.user_id, "email": p.email}))


class MyTicket(BaseModel):
    ticket_id: str


@router.get("/me/tickets", response_model=list[MyTicket], tags=["auth"])
def my_tickets(p: Principal = Depends(require_active)):
    """Tickets an admin has linked to this citizen. Staff accounts get an empty list (they use the queue)."""
    if p.role != "citizen":
        return []
    return [MyTicket(ticket_id=t) for t in p.ticket_ids]


def _user_dict(r) -> dict:
    return {"user_id": r["user_id"], "email": r["email"], "role": r["role"], "status": r["status"],
            "requested_role": r["requested_role"], "created_at": r["created_at"],
            "ticket_ids": _tickets_of(r["user_id"])}


@router.get("/admin/users", tags=["admin"])
def list_users(status: str | None = None, role: str | None = None, _: Principal = Depends(require_admin)):
    q, args = "SELECT * FROM app_users WHERE 1=1", []
    if status:
        q, args = q + " AND status=?", args + [status]
    if role:
        q, args = q + " AND role=?", args + [role]
    return [_user_dict(r) for r in get_conn().execute(q + " ORDER BY created_at", tuple(args)).fetchall()]


def _target(user_id: str):
    row = get_conn().execute("SELECT * FROM app_users WHERE user_id=?", (user_id,)).fetchone()
    if row is None:
        raise api_error(404, "not_found", "No such user.")
    return row


def _set(user_id: str, role: str | None, status: str, actor: Principal, event: str) -> dict:
    with lock():
        row = _target(user_id)
        get_conn().execute("UPDATE app_users SET role=?, status=?, updated_at=?, decided_by=?, decided_at=? WHERE user_id=?",
                           (role or row["role"], status, now_iso(), actor.user_id, now_iso(), user_id))
        get_conn().commit()
        out = _user_dict(_target(user_id))
    audit.append(event, {"user_id": user_id, "role": out["role"], "status": out["status"], "by": actor.user_id})
    return out


@router.post("/admin/users/{user_id}/approve", tags=["admin"])
def approve_user(user_id: str, actor: Principal = Depends(require_admin)):
    """Approve a pending officer request. Citizens and admins are unaffected."""
    row = _target(user_id)
    if row["status"] != "pending" or row["role"] != "officer":
        raise api_error(409, "not_pending", "This user has no pending officer request.")
    return _set(user_id, "officer", "active", actor, "user_approved")


@router.post("/admin/users/{user_id}/reject", tags=["admin"])
def reject_user(user_id: str, actor: Principal = Depends(require_admin)):
    row = _target(user_id)
    if row["role"] == "admin" and row["status"] == "active":
        raise api_error(409, "cannot_reject_admin", "Change the role first.")
    return _set(user_id, "citizen", "rejected", actor, "user_rejected")


class RoleRequest(BaseModel):
    role: Role


@router.post("/admin/users/{user_id}/role", tags=["admin"])
def set_role(user_id: str, req: RoleRequest, actor: Principal = Depends(require_admin)):
    if user_id == actor.user_id and req.role != "admin":
        raise api_error(409, "cannot_demote_self", "Ask another admin to change your role.")
    return _set(user_id, req.role, "active", actor, "user_role_set")


class LinkRequest(BaseModel):
    ticket_id: str


@router.post("/admin/users/{user_id}/tickets", tags=["admin"])
def link_ticket(user_id: str, req: LinkRequest, actor: Principal = Depends(require_admin)):
    """Give a citizen sight of one of their tickets. Citizens cannot do this themselves."""
    valid_ticket_id(req.ticket_id)
    with lock():
        _target(user_id)
        get_conn().execute("DELETE FROM user_tickets WHERE user_id=? AND ticket_id=?", (user_id, req.ticket_id))
        get_conn().execute("INSERT INTO user_tickets (user_id, ticket_id, linked_by, created_at) VALUES (?,?,?,?)",
                           (user_id, req.ticket_id, actor.user_id, now_iso()))
        get_conn().commit()
    audit.append("ticket_linked", {"user_id": user_id, "ticket_id": req.ticket_id, "by": actor.user_id})
    return {"user_id": user_id, "ticket_ids": _tickets_of(user_id)}


@router.delete("/admin/users/{user_id}/tickets/{ticket_id}", tags=["admin"])
def unlink_ticket(user_id: str, ticket_id: str, actor: Principal = Depends(require_admin)):
    with lock():
        _target(user_id)
        get_conn().execute("DELETE FROM user_tickets WHERE user_id=? AND ticket_id=?", (user_id, ticket_id))
        get_conn().commit()
    audit.append("ticket_unlinked", {"user_id": user_id, "ticket_id": ticket_id, "by": actor.user_id})
    return {"user_id": user_id, "ticket_ids": _tickets_of(user_id)}
