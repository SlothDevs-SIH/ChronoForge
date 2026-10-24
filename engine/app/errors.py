"""Request ids, JSON logs and the error envelope {"error": {"code", "message"}, "request_id"} for every non-2xx."""
import json
import logging
import sys
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed",
         409: "conflict", 413: "payload_too_large", 422: "validation_error", 429: "rate_limited",
         500: "internal_error", 503: "unavailable"}

log = logging.getLogger("trueclose.engine")


def configure_logging() -> None:
    if log.handlers:
        return
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)
    log.propagate = False


def _envelope(request: Request, status: int, message: str, code: str | None = None) -> JSONResponse:
    rid = getattr(request.state, "request_id", "")
    resp = JSONResponse({"error": {"code": code or CODES.get(status, "error"), "message": message}, "request_id": rid}, status_code=status)
    resp.headers["X-Request-ID"] = rid
    return resp


def install(app: FastAPI) -> None:
    configure_logging()

    @app.middleware("http")
    async def request_id_and_log(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        t0 = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:   # the exception handler below turns this into a 500 envelope
            log.exception(json.dumps({"event": "unhandled", "request_id": rid, "path": request.url.path}))
            response = _envelope(request, 500, "something went wrong on our side")
        response.headers["X-Request-ID"] = rid
        log.info(json.dumps({"event": "request", "request_id": rid, "method": request.method, "path": request.url.path,
                             "status": response.status_code or status, "ms": round((time.perf_counter() - t0) * 1000),
                             "user": getattr(request.state, "user_id", None)}))
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException):
        return _envelope(request, exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        return _envelope(request, 422, f"{where or 'request'}: {first.get('msg', 'invalid value')}")

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception(json.dumps({"event": "unhandled", "request_id": getattr(request.state, "request_id", ""), "path": request.url.path}))
        return _envelope(request, 500, "something went wrong on our side")
