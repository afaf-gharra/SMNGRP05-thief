"""The Gatekeeper's other two gates: the daily quota and the runaway-loop detector.

The token bucket smooths traffic; these two stop it entirely.

* :class:`QuotaManager` is the last line before account suspension. It counts
  calls per day against a hard ceiling and, once spent, lets nothing through.
* :class:`DosDetector` watches the *shape* of traffic rather than its volume. A
  burst far above anything a real match produces is not demand — it is a bug,
  usually an infinite loop. The detector latches shut (a circuit breaker) and
  sacrifices the remaining reports to save the account they would be sent from.
"""

import threading
import time
from collections import deque
from datetime import UTC, datetime


class QuotaManager:
    """Counts calls against a per-day ceiling."""

    def __init__(self, daily_quota: int, clock=None) -> None:
        self.daily_quota = int(daily_quota)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._day = self._today()
        self._used = 0
        self._lock = threading.Lock()

    def _today(self) -> str:
        return self._clock().strftime("%Y-%m-%d")

    @property
    def used(self) -> int:
        with self._lock:
            self._roll()
            return self._used

    @property
    def remaining(self) -> int:
        return max(0, self.daily_quota - self.used)

    def _roll(self) -> None:
        today = self._today()
        if today != self._day:
            self._day, self._used = today, 0

    def allow(self) -> bool:
        with self._lock:
            self._roll()
            if self._used >= self.daily_quota:
                return False
            self._used += 1
            return True


class DosDetector:
    """Latching circuit breaker for anomalous outbound bursts."""

    def __init__(self, window_seconds: float, max_in_window: int, clock=time.monotonic) -> None:
        self.window_seconds = float(window_seconds)
        self.max_in_window = int(max_in_window)
        self._clock = clock
        self._events: deque[float] = deque()
        self._locked = False
        self._lock = threading.Lock()

    @property
    def locked(self) -> bool:
        return self._locked

    def reset(self) -> None:
        """Manual re-arm after a human has looked at the logs. Never automatic."""
        with self._lock:
            self._locked = False
            self._events.clear()

    def allow(self) -> bool:
        """Record one call; return ``False`` once the breaker has tripped."""
        with self._lock:
            if self._locked:
                return False
            now = self._clock()
            self._events.append(now)
            cutoff = now - self.window_seconds
            while self._events and self._events[0] < cutoff:
                self._events.popleft()
            if len(self._events) > self.max_in_window:
                self._locked = True
                return False
            return True

    def status(self) -> dict:
        return {
            "locked": self._locked,
            "in_window": len(self._events),
            "max_in_window": self.max_in_window,
            "window_seconds": self.window_seconds,
        }
