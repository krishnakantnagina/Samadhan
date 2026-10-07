"""Login lockout for the dashboards (audit H6).

The dashboards are on a public address and every wrong password costs the server a 200,000-round PBKDF2. Without a limit, anyone can guess passwords or
burn the server's CPU. This keeps, in this process:
  * a per-username counter: MAX_FAILURES wrong tries inside WINDOW seconds lock that username for LOCK seconds;
  * a global counter (all usernames together, so spraying many names is slowed too): GLOBAL_MAX_FAILURES inside WINDOW locks every login for LOCK seconds.
While locked, the password is not even checked (no CPU spent), and a correct password does not unlock early. A success clears that username's failures.
In-memory on purpose: it resets on restart and is per server process; for several servers put the counters in the database.
"""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

MAX_FAILURES = 5
GLOBAL_MAX_FAILURES = 40
WINDOW_SECONDS = 600.0
LOCK_SECONDS = 600.0


class LoginThrottle:
    def __init__(
        self,
        *,
        max_failures: int = MAX_FAILURES,
        global_max_failures: int = GLOBAL_MAX_FAILURES,
        window: float = WINDOW_SECONDS,
        lock: float = LOCK_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max, self._global_max, self._window, self._lock_for, self._clock = max_failures, global_max_failures, window, lock, clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._global: deque[float] = deque()
        self._locked_until: dict[str, float] = {}
        self._global_locked_until = 0.0
        self._mutex = threading.Lock()

    @staticmethod
    def _key(username: str) -> str:
        return (username or "").strip().lower()[:80]

    def _trim(self, q: deque[float], now: float) -> None:
        while q and now - q[0] > self._window:
            q.popleft()

    def seconds_locked(self, username: str) -> int:
        """0 when the login may be tried, else the whole seconds still to wait."""
        now = self._clock()
        with self._mutex:
            until = max(self._locked_until.get(self._key(username), 0.0), self._global_locked_until)
            return max(0, int(until - now) + 1) if until > now else 0

    def record_failure(self, username: str) -> None:
        now, key = self._clock(), self._key(username)
        with self._mutex:
            mine = self._failures[key]
            mine.append(now)
            self._trim(mine, now)
            self._global.append(now)
            self._trim(self._global, now)
            if len(mine) >= self._max:
                self._locked_until[key] = now + self._lock_for
                mine.clear()
            if len(self._global) >= self._global_max:
                self._global_locked_until = now + self._lock_for
                self._global.clear()

    def record_success(self, username: str) -> None:
        with self._mutex:
            key = self._key(username)
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)


LOGIN_THROTTLE = LoginThrottle()


def locked_message(seconds: int) -> str:
    minutes = max(1, (seconds + 59) // 60)
    return f"Too many wrong attempts. Please try again in about {minutes} minute(s)."
