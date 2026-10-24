"""Sliding-window counter for limits that are not an HTTP endpoint (for example photos sent in the bot chat). HTTP
endpoints use http_utils.rate_limit. One process, so counts are per instance."""
import threading
import time
from collections import defaultdict, deque

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
        if len(_hits) > 50_000:   # forget idle keys so a scan of many chats cannot grow memory without bound
            for k in [k for k, v in _hits.items() if not v or v[-1] <= now - window][:10_000]:
                _hits.pop(k, None)
        return True


def reset() -> None:
    with _lock:
        _hits.clear()
