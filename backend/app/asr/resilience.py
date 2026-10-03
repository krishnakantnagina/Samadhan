"""S32 -- load-protection building blocks: rate limiter, circuit breaker, bulkhead, metrics.

All thread-safe (FastAPI runs sync handlers in a thread pool) and all take an injectable clock/sleep so the
tests run instantly. No third-party libraries.
"""

import math
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable


class TokenBucket:
    """Smooths calls to a provider to its quota. `rate_per_minute` None or 0 = unlimited.

    acquire() waits (up to max_wait seconds) for a token instead of failing straight away, so a short spike is
    absorbed; it returns False when waiting would take longer, and the router moves to the next provider.
    """

    def __init__(
        self,
        rate_per_minute: float | None,
        *,
        burst: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._unlimited = not rate_per_minute
        self._rate = (rate_per_minute or 0) / 60.0  # tokens per second
        self._capacity = burst if burst is not None else max(1.0, math.ceil(self._rate * 2))
        self._tokens = self._capacity
        self._clock = clock
        self._sleep = sleep
        self._last = clock()
        self._lock = threading.Lock()

    def acquire(self, max_wait: float = 0.0) -> bool:
        if self._unlimited:
            return True
        deadline = self._clock() + max_wait
        while True:
            with self._lock:
                now = self._clock()
                self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate)
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
                need = (1.0 - self._tokens) / self._rate
            if now + need > deadline:
                return False
            self._sleep(need)


class CircuitBreaker:
    """closed -> (N failures in a row) -> open -> (cooldown) -> half-open: ONE probe call -> closed or open again.

    While open the provider is skipped without any call, so a dead provider costs nothing and the citizen is not
    kept waiting on it. A `cooldown` override opens it for longer (credit exhausted, key revoked).
    """

    CLOSED, OPEN, HALF_OPEN = "closed", "open", "half_open"

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        cooldown_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._state = self.CLOSED
        self._failures = 0
        self._opened_until = 0.0
        self._probe_in_flight = False

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def is_open(self) -> bool:
        """Side-effect-free peek: True while calls would be refused (open and still cooling down)."""
        with self._lock:
            if self._state == self.OPEN and self._clock() < self._opened_until:
                return True
            return self._state == self.HALF_OPEN and self._probe_in_flight

    def allow(self) -> bool:
        """Ask permission for one call. In half-open exactly one caller gets True (the probe)."""
        with self._lock:
            if self._state == self.CLOSED:
                return True
            if self._state == self.OPEN:
                if self._clock() < self._opened_until:
                    return False
                self._state = self.HALF_OPEN
                self._probe_in_flight = True
                return True
            if self._probe_in_flight:
                return False
            self._probe_in_flight = True
            return True

    def record_success(self) -> None:
        with self._lock:
            self._state = self.CLOSED
            self._failures = 0
            self._probe_in_flight = False

    def record_failure(self, *, cooldown: float | None = None) -> None:
        with self._lock:
            self._failures += 1
            if cooldown is not None or self._state == self.HALF_OPEN or self._failures >= self._threshold:
                self._state = self.OPEN
                self._opened_until = self._clock() + (cooldown if cooldown is not None else self._cooldown)
                self._probe_in_flight = False

    def release_probe(self) -> None:
        """A permitted call was never made (e.g. no capacity): free the half-open probe slot."""
        with self._lock:
            self._probe_in_flight = False


class Bulkhead:
    """Caps simultaneous in-flight calls to one provider, so a slow provider cannot eat every worker thread."""

    def __init__(self, max_concurrent: int) -> None:
        self._sem = threading.BoundedSemaphore(max_concurrent)

    def acquire(self, timeout: float = 0.0) -> bool:
        return self._sem.acquire(timeout=max(0.0, timeout)) if timeout > 0 else self._sem.acquire(blocking=False)

    def release(self) -> None:
        self._sem.release()


class Metrics:
    """In-memory counters and latency samples per provider. snapshot() is what a future /metrics endpoint serves."""

    def __init__(self, keep: int = 500) -> None:
        self._lock = threading.Lock()
        self._counts: dict[tuple[str, str], int] = defaultdict(int)
        self._latency: dict[str, deque[int]] = defaultdict(lambda: deque(maxlen=keep))

    def count(self, provider: str, outcome: str) -> None:
        with self._lock:
            self._counts[(provider, outcome)] += 1

    def observe_latency(self, provider: str, ms: int) -> None:
        with self._lock:
            self._latency[provider].append(ms)

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            out: dict[str, dict] = {}
            for (provider, outcome), n in self._counts.items():
                out.setdefault(provider, {"outcomes": {}})["outcomes"][outcome] = n
            for provider, samples in self._latency.items():
                ordered = sorted(samples)
                entry = out.setdefault(provider, {"outcomes": {}})
                if ordered:
                    entry["latency_ms_p50"] = ordered[len(ordered) // 2]
                    entry["latency_ms_p95"] = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
            return out
