"""Small in-memory sliding-window limiter against floods and password guessing. One process, so it is per instance:
behind several workers each keeps its own counts, which is still enough to stop a single client hammering an endpoint."""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from . import config

_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def allow(key: str, limit: int, window: float, now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    with _lock:
        q = _hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        if len(_hits) > 50_000:   # forget idle keys so a scan of many addresses cannot grow memory without bound
            for k in [k for k, v in _hits.items() if not v or v[-1] <= now - window][:10_000]:
                _hits.pop(k, None)
        return True


def reset() -> None:
    with _lock:
        _hits.clear()


def client_ip(request: Request) -> str:
    if config.TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def limit(name: str, count: int, window: float):
    """FastAPI dependency: at most `count` calls per `window` seconds per client address."""
    def dep(request: Request):
        if config.RATE_LIMIT and not allow(f"{name}:{client_ip(request)}", count, window):
            raise HTTPException(429, "too many attempts, wait a moment and try again")
    return dep


def check_user(name: str, user_id: str, count: int, window: float) -> None:
    if config.RATE_LIMIT and not allow(f"{name}:u:{user_id}", count, window):
        raise HTTPException(429, "you are doing that too often, try again later")
