"""Authentication and authorisation for the Engine (contract/AUTH_AND_DEPLOY.md).

Identity: a Supabase access token, verified here (signature, expiry, audience). Role: looked up from the Agent
(`GET {AGENT_URL}/auth/me`, forwarding the same bearer token) because the Agent owns the users table. The answer is
cached for 60 seconds. If the Agent cannot be reached the request fails with 503; access is never granted by default.

AUTH_REQUIRED=0 (default) keeps the laptop demo and the existing tests open. Set AUTH_REQUIRED=1 in production.
"""
import hashlib
import hmac
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import httpx
import jwt
from fastapi import Depends, Header, HTTPException, Request

ROLE_CACHE_SECONDS = 10   # short, so a ticket a citizen just filed (linked to them) is readable within seconds
_cache: dict[str, tuple[float, "Principal"]] = {}
_cache_lock = threading.Lock()
_jwk_client: Optional[jwt.PyJWKClient] = None


@dataclass
class Principal:
    anonymous: bool = True
    user_id: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None          # citizen | officer | admin
    status: Optional[str] = None        # active | pending | rejected
    ticket_ids: list[str] = field(default_factory=list)
    local_open: bool = False            # AUTH_REQUIRED=0: everything is allowed (laptop demo)
    service: bool = False               # the Agent, identified by ENGINE_SERVICE_TOKEN (read access to tickets and checks)

    @property
    def active(self) -> bool:
        return self.local_open or (not self.anonymous and self.status == "active")

    def has_role(self, *roles: str) -> bool:
        return self.local_open or (self.active and self.role in roles)


def auth_required() -> bool:
    return os.environ.get("AUTH_REQUIRED", "0") == "1"


def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, message)


# ---- token verification ----
def verify_token(token: str) -> dict:
    """Return the verified claims or raise 401. HS256 with SUPABASE_JWT_SECRET, else the project's JWKS."""
    global _jwk_client
    audience = os.environ.get("SUPABASE_JWT_AUDIENCE", "authenticated")
    secret = os.environ.get("SUPABASE_JWT_SECRET", "")
    options = {"require": ["exp", "sub"]}
    try:
        if secret:
            return jwt.decode(token, secret, algorithms=["HS256"], audience=audience, options=options)
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        if not url:
            raise _err(503, "authentication is not configured on this service")
        if _jwk_client is None or getattr(_jwk_client, "_tc_url", None) != url:
            _jwk_client = jwt.PyJWKClient(f"{url}/auth/v1/.well-known/jwks.json", cache_keys=True, lifespan=3600)
            _jwk_client._tc_url = url  # type: ignore[attr-defined]
        key = _jwk_client.get_signing_key_from_jwt(token).key
        return jwt.decode(token, key, algorithms=["ES256", "RS256"], audience=audience, options=options)
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise _err(401, "the session has expired; sign in again")
    except jwt.PyJWKClientConnectionError:
        raise _err(503, "could not fetch the signing keys; try again shortly")
    except jwt.PyJWTError:
        raise _err(401, "the access token is not valid")


# ---- role lookup (the Agent owns the users table) ----
def _lookup_profile(token: str) -> dict:
    base = os.environ.get("AGENT_URL", "").rstrip("/")
    if not base:
        raise _err(503, "the Agent URL is not configured, so roles cannot be checked")
    try:
        r = httpx.get(f"{base}/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=5.0)
    except httpx.HTTPError:
        raise _err(503, "the Agent is not reachable, so roles cannot be checked")
    if r.status_code in (401, 403):
        raise _err(401, "the access token was not accepted")
    if r.status_code != 200:
        raise _err(503, "the Agent could not answer the role check")
    return r.json()


def principal_from_token(token: str, fresh: bool = False) -> Principal:
    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and not fresh and now - hit[0] < ROLE_CACHE_SECONDS:
            return hit[1]
    claims = verify_token(token)
    profile = _lookup_profile(token)
    p = Principal(anonymous=False, user_id=str(profile.get("user_id") or claims["sub"]), email=profile.get("email") or claims.get("email"),
                  role=profile.get("role"), status=profile.get("status"), ticket_ids=list(profile.get("ticket_ids") or []))
    with _cache_lock:
        _cache[key] = (now, p)
        if len(_cache) > 2000:
            _cache.clear()
    return p


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def get_principal(request: Request, authorization: Optional[str] = Header(default=None),
                  x_service_token: Optional[str] = Header(default=None)) -> Principal:
    if not auth_required():
        return Principal(anonymous=False, role="admin", status="active", local_open=True)
    service_token = os.environ.get("ENGINE_SERVICE_TOKEN", "")
    if service_token and x_service_token and hmac.compare_digest(x_service_token, service_token):
        return Principal(anonymous=False, user_id="agent-service", role="service", status="active", service=True)
    if not authorization:
        return Principal()
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _err(401, "send the access token as 'Authorization: Bearer <token>'")
    p = principal_from_token(token.strip())
    request.state.user_id = p.user_id
    return p


def _deny(p: Principal) -> HTTPException:
    if p.anonymous:
        return _err(401, "sign in to use this endpoint")
    if p.status != "active":
        return _err(403, "this account is not active yet")
    return _err(403, "your role is not allowed to use this endpoint")


# ---- dependencies (one per row of the permission matrix) ----
def public(p: Principal = Depends(get_principal)) -> Principal:
    return p


def staff(p: Principal = Depends(get_principal)) -> Principal:
    """officer or admin, or the Agent service."""
    if not p.service and not p.has_role("officer", "admin"):
        raise _deny(p)
    return p


def admin_only(p: Principal = Depends(get_principal)) -> Principal:
    if not p.has_role("admin"):
        raise _deny(p)
    return p


def ticket_reader(ticket_id: str, request: Request, p: Principal = Depends(get_principal)) -> Principal:
    """officer or admin (or the Agent service) for any ticket; a citizen only for a ticket linked to them."""
    if p.service or p.has_role("officer", "admin"):
        return p
    if p.has_role("citizen") and ticket_id in p.ticket_ids:
        return p
    if p.has_role("citizen"):
        # the cached profile can predate a link made a moment ago (a citizen who just filed this request): ask once more
        scheme, _, token = (request.headers.get("authorization") or "").partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            current = principal_from_token(token.strip(), fresh=True)
            if current.has_role("citizen") and ticket_id in current.ticket_ids:
                return current
        raise _err(403, "this ticket is not linked to your account")
    raise _deny(p)


def admin_or_token(x_admin_token: Optional[str] = Header(default=None), p: Principal = Depends(get_principal)) -> Principal:
    """Connector sync: an admin, or the shared ENGINE_ADMIN_TOKEN (kept for scripts). With AUTH_REQUIRED=0 and no
    token set it stays open, as before (laptop demo only)."""
    token = os.environ.get("ENGINE_ADMIN_TOKEN", "")
    if token and x_admin_token and hmac.compare_digest(x_admin_token, token):
        return p
    if p.local_open:
        if token:
            raise _err(403, "admin token required")
        return p
    if p.has_role("admin"):
        return p
    raise _deny(p)


def service_caller(x_service_token: Optional[str] = Header(default=None), p: Principal = Depends(get_principal)) -> Principal:
    """The simulated municipal system: only the Agent (shared ENGINE_SERVICE_TOKEN). Fails closed when the token is
    unset and auth is required. Open with AUTH_REQUIRED=0, for the laptop demo and local tests."""
    if not auth_required():
        return p
    token = os.environ.get("ENGINE_SERVICE_TOKEN", "")
    if not token:
        raise _err(503, "ENGINE_SERVICE_TOKEN is not configured")
    if not x_service_token or not hmac.compare_digest(x_service_token, token):
        raise _err(403, "service token required")
    return p
