"""Token-bucket rate limiter (book ch.9, Appendix F table 19).

    tokens <- min(C, tokens + r * dt),   allow  <=>  tokens >= 1

The bucket separates two things a single "requests per minute" number confuses:
the sustainable long-run rate ``r``, and the burst ``C`` you may spend at once
after a quiet spell. Silence is rewarded with capacity; a runaway loop drains the
bucket in seconds and is then throttled to exactly ``r`` — which is the whole
point, because an autonomous agent with a bug is otherwise perfectly capable of
getting its owner's mail account suspended before anyone notices.

"Token" here means a *rate* token and has nothing to do with language-model
tokens; the book warns explicitly about that collision of terms.
"""

import threading
import time


class TokenBucket:
    """Thread-safe token bucket."""

    def __init__(self, capacity: float, refill_rate: float, clock=time.monotonic) -> None:
        if capacity <= 0 or refill_rate <= 0:
            raise ValueError("Token bucket capacity and refill rate must both be positive")
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self._clock = clock
        self._tokens = float(capacity)  # start full: a fresh agent may act at once
        self._last = clock()
        self._lock = threading.Lock()

    @property
    def tokens(self) -> float:
        with self._lock:
            self._refill()
            return round(self._tokens, 4)

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last)
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
        self._last = now

    def allow(self, cost: float = 1.0) -> bool:
        """Spend a token and return ``True``, or return ``False`` without spending."""
        with self._lock:
            self._refill()
            if self._tokens >= cost:
                self._tokens -= cost
                return True
            return False

    def wait_time(self, cost: float = 1.0) -> float:
        """Seconds until ``cost`` tokens are available — so callers back off by fact."""
        with self._lock:
            self._refill()
            if self._tokens >= cost:
                return 0.0
            return (cost - self._tokens) / self.refill_rate

    @classmethod
    def per_minute(cls, requests_per_minute: float, burst: float | None = None) -> "TokenBucket":
        """Build from the units the config actually uses."""
        rate = max(1e-6, float(requests_per_minute) / 60.0)
        return cls(capacity=burst or max(1.0, requests_per_minute / 6.0), refill_rate=rate)
