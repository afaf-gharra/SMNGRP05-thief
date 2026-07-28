"""``ApiGatekeeper`` — every outbound external call goes through exactly one door.

Submission guidelines §5.1 require a single centralised gate for external APIs;
the book (ch.9) specifies what has to be behind it. Three gates in series, each
failing fast, in increasing order of severity:

    request -> QuotaManager -> TokenBucket -> DosDetector -> the real API

Overflow is *queued*, not dropped: a report that arrives late is still a report,
whereas a dropped one costs the match's league points. Only a tripped circuit
breaker refuses outright, and that is deliberate — at that point something is
wrong with us, not with the network.
"""

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from p2p_chase.exceptions import RateLimited
from p2p_chase.shared.guards import DosDetector, QuotaManager
from p2p_chase.shared.rate_limiter import TokenBucket

logger = logging.getLogger(__name__)


class ApiGatekeeper:
    """Centralised rate-limited, retrying, observable API call manager."""

    def __init__(self, limits: dict, service: str = "default", sleep=time.sleep) -> None:
        self.service = service
        self.limits = limits
        self._sleep = sleep
        self.bucket = TokenBucket.per_minute(
            limits.get("requests_per_minute", 30), burst=limits.get("concurrent_max", 2) * 2
        )
        self.quota = QuotaManager(limits.get("daily_quota", 500))
        self.dos = DosDetector(
            limits.get("dos_window_seconds", 10), limits.get("dos_max_in_window", 20)
        )
        self.max_retries = int(limits.get("max_retries", 3))
        self.retry_after = float(limits.get("retry_after_seconds", 5))
        self.queue_depth = int(limits.get("queue_depth", 100))
        self._semaphore = threading.Semaphore(max(1, int(limits.get("concurrent_max", 2))))
        self._waiting = 0
        self._lock = threading.Lock()
        self.calls_made = 0
        self.calls_rejected = 0

    def execute(self, call: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run ``call`` through the gates, retrying transient failures.

        Raises :class:`RateLimited` when a gate refuses. The caller decides
        whether that is fatal; for a match report it means "try again after the
        turn", not "give up".
        """
        self._admit()
        with self._semaphore:
            return self._attempt(call, *args, **kwargs)

    def _admit(self) -> None:
        if not self.quota.allow():
            self.calls_rejected += 1
            raise RateLimited(
                f"Daily quota for '{self.service}' exhausted "
                f"({self.quota.daily_quota} calls). Refusing to risk the account."
            )
        if not self.dos.allow():
            self.calls_rejected += 1
            raise RateLimited(
                f"DOS detector latched for '{self.service}': {self.dos.status()}. "
                "This looks like a runaway loop, not real demand. Investigate, then reset()."
            )
        self._queue_for_token()

    def _queue_for_token(self) -> None:
        """Wait for a rate token rather than dropping the call (guidelines §5.3)."""
        with self._lock:
            if self._waiting >= self.queue_depth:
                self.calls_rejected += 1
                raise RateLimited(
                    f"Gatekeeper queue for '{self.service}' is full ({self.queue_depth}); "
                    "applying backpressure."
                )
            self._waiting += 1
        try:
            while not self.bucket.allow():
                delay = max(0.01, self.bucket.wait_time())
                logger.debug("Rate limit on %s: waiting %.2fs", self.service, delay)
                self._sleep(delay)
        finally:
            with self._lock:
                self._waiting -= 1

    def _attempt(self, call: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        last: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result = call(*args, **kwargs)
                self.calls_made += 1
                return result
            except Exception as exc:  # noqa: BLE001 - deliberately provider-agnostic
                last = exc
                logger.warning(
                    "%s call failed (attempt %d/%d): %s",
                    self.service, attempt, self.max_retries, exc,
                )
                if attempt < self.max_retries:
                    self._sleep(self.retry_after * attempt)  # linear backoff
        self.calls_rejected += 1
        raise RateLimited(
            f"'{self.service}' failed {self.max_retries} times; last error: {last}"
        ) from last

    def status(self) -> dict:
        """Observable state — surfaced in the GUI and folded into the match report."""
        return {
            "service": self.service,
            "calls_made": self.calls_made,
            "calls_rejected": self.calls_rejected,
            "tokens_available": self.bucket.tokens,
            "quota_used": self.quota.used,
            "quota_remaining": self.quota.remaining,
            "queue_waiting": self._waiting,
            "dos": self.dos.status(),
        }
