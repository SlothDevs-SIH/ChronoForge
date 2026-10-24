"""HTTP hygiene shared by every endpoint: one JSON error shape, a request id on every response, structured JSON logs and a
small in-memory rate limiter.

Error shape (every non-2xx response):  {"error": {"code": "...", "message": "..."}, "request_id": "..."}
The limiter is per process (fine for one Render instance; use a shared store before scaling out).
"""
import contextvars
import json
import logging
import re
import threading
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import config

_ctx: contextvars.ContextVar[dict | None] = contextvars.ContextVar("request_ctx", default=None)
_SAFE_ID = re.compile(r"^[A-Za-z0-9._\-]{8,64}$")

_CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed",
          409: "conflict", 410: "gone", 413: "payload_too_large", 415: "unsupported_media_type",
          422: "validation_error", 429: "rate_limited", 500: "internal_error", 503: "unavailable"}


def api_error(status: int, code: str, message: str, headers: dict | None = None) -> HTTPException:
    """Raise this for any error that should carry a specific machine-readable code."""
    return HTTPException(status_code=status, detail={"code": code, "message": message}, headers=headers)


def request_id() -> str:
    c = _ctx.get()
    return c["request_id"] if c else "-"


def note_user(user_id: str | None) -> None:
    """Called by the auth layer so the access log can say who made the request."""
    c = _ctx.get()
    if c is not None:
        c["user"] = user_id


def _envelope(status: int, code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}, "request_id": request_id()}


# ---- structured logs ----------------------------------------------------------------------------------------------
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z", "level": record.levelname,
               "logger": record.name, "msg": record.getMessage()}
        for k in ("request_id", "method", "path", "status", "ms", "user"):
            if hasattr(record, k):
                out[k] = getattr(record, k)
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def setup_logging() -> None:
    """One JSON line per log record on stdout. Idempotent."""
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    root.handlers = [h]
    root.setLevel(logging.INFO)
    # httpx logs the full URL of every request at INFO, and a Telegram request URL contains the bot token
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


access_log = logging.getLogger("trueclose.access")


class RequestContextMiddleware:
    """Pure ASGI (not BaseHTTPMiddleware) so server-sent event streams are not buffered or cancelled."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        rid = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex
        ctx = {"request_id": rid, "user": None}
        token = _ctx.set(ctx)
        started, status = time.perf_counter(), {"code": 0, "sent": False}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"], status["sent"] = message["status"], True
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", rid.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            # Starlette's outermost layer would answer this after we have left (no request id, no log context), so
            # an unexpected error is turned into the standard 500 here, inside the request.
            logging.getLogger("trueclose.error").error("unhandled error", exc_info=exc, extra={"request_id": rid})
            if status["sent"]:
                raise
            body = json.dumps(_envelope(500, "internal_error", "Something went wrong on our side. Try again.")).encode()
            await send_wrapper({"type": "http.response.start", "status": 500,
                                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
            await send_wrapper({"type": "http.response.body", "body": body})
        finally:
            # the path only: query strings can carry tokens and are never logged
            access_log.info("request", extra={"request_id": rid, "method": scope["method"], "path": scope["path"],
                                              "status": status["code"], "ms": round((time.perf_counter() - started) * 1000),
                                              "user": ctx["user"]})
            _ctx.reset(token)


# ---- error handlers -----------------------------------------------------------------------------------------------
def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            code, message = detail["code"], detail.get("message", "")
        else:
            code, message = _CODES.get(exc.status_code, "error"), str(detail)
        return JSONResponse(_envelope(exc.status_code, code, message), status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        message = f"{where}: {first.get('msg', 'invalid request')}" if where else first.get("msg", "invalid request")
        return JSONResponse(_envelope(422, "validation_error", message), status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logging.getLogger("trueclose.error").error("unhandled error", exc_info=exc, extra={"request_id": request_id()})
        return JSONResponse(_envelope(500, "internal_error", "Something went wrong on our side. Try again."),
                            status_code=500)


# ---- rate limiting ------------------------------------------------------------------------------------------------
_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def reset_rate_limits() -> None:
    with _hits_lock:
        _hits.clear()


def client_address(request: Request) -> str:
    if config.TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(name: str, limit: int, window_seconds: int):
    """FastAPI dependency: at most `limit` calls per `window_seconds` per caller (user id if known, else address)."""
    def dependency(request: Request) -> None:
        if not config.RATE_LIMITS_ENABLED:
            return
        c = _ctx.get() or {}
        who = c.get("user") or client_address(request)
        key, now = f"{name}:{who}", time.monotonic()
        with _hits_lock:
            q = _hits[key]
            while q and now - q[0] > window_seconds:
                q.popleft()
            if len(q) >= limit:
                retry = max(1, int(window_seconds - (now - q[0])))
                raise api_error(429, "rate_limited", f"Too many requests. Try again in {retry} seconds.",
                                headers={"Retry-After": str(retry)})
            q.append(now)
    return dependency
