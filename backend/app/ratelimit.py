"""Request rate limits (audit H4): stop one client from burning the paid speech / LLM / transcription credit or flooding the database.

Sliding window, in this process only (it resets on restart and is not shared between several server processes: for that, use a gateway or Redis).
Limits are per minute, per key. Two kinds of key:
  * the caller's IP address (`/speak`, `/status`, `/auth/*`, and the first line of defence on `/message`);
  * the chat session id (`/message`): a village can sit behind ONE shared mobile-network address, so the per-IP numbers are generous and the per-session
    number is the one that protects the credit.

Defaults (per minute) can be changed with RATE_LIMIT_<NAME>, and 0 turns that limit off; RATE_LIMIT_DISABLED=1 turns all of them off (tests, local runs):
  message 60 per IP, message_session 20 per session, speak 60 per IP, status 120 per IP, auth_start 20 per IP, auth_verify 40 per IP.
Behind a proxy (Render, Railway) set TRUST_FORWARDED_FOR=1 so the first X-Forwarded-For address is used instead of the proxy's own.
"""

import os
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import Request

from app import schemas as api
from mock.errors import ApiError

DEFAULTS = {"message": 60, "message_session": 20, "speak": 60, "status": 120, "auth_start": 20, "auth_verify": 40}
WINDOW_SECONDS = 60.0
MAX_KEYS = 20000  # bound the memory: past this, idle keys are dropped


class SlidingWindow:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: float = WINDOW_SECONDS) -> tuple[bool, int]:
        """Record one request. (allowed, seconds to wait when refused)."""
        now = self._clock()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] >= window:
                q.popleft()
            if len(q) >= limit:
                return False, max(1, int(window - (now - q[0])) + 1)
            q.append(now)
            if len(self._hits) > MAX_KEYS:
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= window][: MAX_KEYS // 2]:
                    del self._hits[k]
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


_windows: dict[str, SlidingWindow] = {}
_windows_lock = threading.Lock()


def reset() -> None:
    """Forget every counter (tests)."""
    with _windows_lock:
        _windows.clear()


def disabled() -> bool:
    return os.environ.get("RATE_LIMIT_DISABLED", "").strip().lower() in ("1", "true", "yes", "on")


def limit_for(name: str) -> int:
    raw = os.environ.get(f"RATE_LIMIT_{name.upper()}", "").strip()
    try:
        return max(0, int(raw)) if raw else DEFAULTS[name]
    except ValueError:
        return DEFAULTS[name]


def client_ip(request: Request) -> str:
    if os.environ.get("TRUST_FORWARDED_FOR", "").strip().lower() in ("1", "true", "yes", "on"):
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:64]
    return request.client.host if request.client else "unknown"


def enforce(name: str, key: str) -> None:
    """Count this request against `name` for `key`; raise the 429 the website already understands when it is over the limit."""
    if disabled():
        return
    limit = limit_for(name)
    if limit <= 0:
        return
    with _windows_lock:
        window = _windows.setdefault(name, SlidingWindow())
    allowed, wait = window.hit(key, limit)
    if not allowed:
        raise ApiError(api.ErrorCode.RATE_LIMITED, f"Too many requests. Try again in about {wait} s.")


def limiter(name: str) -> Callable[[Request], None]:
    """A FastAPI dependency: `Depends(limiter("speak"))` limits that route per client IP."""

    def dependency(request: Request) -> None:
        enforce(name, client_ip(request))

    return dependency
