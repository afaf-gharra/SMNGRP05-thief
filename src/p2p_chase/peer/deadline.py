"""``DeadlineTracker`` — a missed deadline is a failure, not patience (rule 6).

The single most dangerous line in a peer-to-peer program is an unbounded wait.
Nothing crashes, nothing logs, and two agents sit politely staring at each other
until someone notices hours later. Every wait in this codebase therefore carries
an explicit expiry, and expiry means *act*: retry, or declare a technical loss
and close the turn cleanly.

Deliberately monotonic-clock based. Wall-clock time can jump backwards when the
machine syncs NTP mid-match, and a deadline that un-expires is worse than none.
"""

import time
from dataclasses import dataclass, field


@dataclass
class Deadline:
    """One bounded wait."""

    budget_seconds: float
    label: str = "operation"
    started: float = field(default_factory=time.monotonic)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    @property
    def remaining(self) -> float:
        return max(0.0, self.budget_seconds - self.elapsed)

    @property
    def expired(self) -> bool:
        return self.remaining <= 0.0

    def reset(self) -> None:
        self.started = time.monotonic()


class DeadlineTracker:
    """Issues deadlines and remembers how often each kind was missed.

    The counters are not decoration: a match report that shows six timeouts
    against one opponent and none against another is how you find out that the
    problem is the network rather than the strategy.
    """

    def __init__(self, default_budget: float = 180.0) -> None:
        self.default_budget = float(default_budget)
        self.expiries: dict[str, int] = {}
        self.completions: dict[str, int] = {}

    def start(self, label: str = "turn", budget: float | None = None) -> Deadline:
        return Deadline(budget_seconds=budget or self.default_budget, label=label)

    def record(self, deadline: Deadline) -> bool:
        """Book-keep a finished wait. Returns ``True`` when it expired."""
        bucket = self.expiries if deadline.expired else self.completions
        bucket[deadline.label] = bucket.get(deadline.label, 0) + 1
        return deadline.expired

    @property
    def total_expiries(self) -> int:
        return sum(self.expiries.values())

    def summary(self) -> dict:
        return {
            "default_budget_seconds": self.default_budget,
            "expiries": dict(self.expiries),
            "completions": dict(self.completions),
            "total_expiries": self.total_expiries,
        }
