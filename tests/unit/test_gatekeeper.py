"""The three gates that stand between an autonomous agent and a suspended account."""

import pytest

from p2p_chase.exceptions import RateLimited
from p2p_chase.shared.gatekeeper import ApiGatekeeper
from p2p_chase.shared.guards import DosDetector, QuotaManager
from p2p_chase.shared.rate_limiter import TokenBucket


class FakeClock:
    """A clock we drive by hand, so rate-limit tests are exact rather than slow."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ------------------------------------------------------------- token bucket


def test_a_bucket_starts_full_so_a_fresh_agent_may_act():
    bucket = TokenBucket(capacity=3, refill_rate=1, clock=FakeClock())
    assert bucket.tokens == 3


@pytest.mark.parametrize("capacity,rate", [(0, 1), (1, 0), (-1, 1)])
def test_a_nonsensical_bucket_is_rejected(capacity, rate):
    with pytest.raises(ValueError, match="must both be positive"):
        TokenBucket(capacity=capacity, refill_rate=rate)


def test_a_burst_drains_the_bucket_and_is_then_throttled():
    clock = FakeClock()
    bucket = TokenBucket(capacity=3, refill_rate=1, clock=clock)
    assert [bucket.allow() for _ in range(3)] == [True, True, True]
    assert bucket.allow() is False


def test_silence_is_rewarded_with_capacity():
    clock = FakeClock()
    bucket = TokenBucket(capacity=3, refill_rate=1, clock=clock)
    for _ in range(3):
        bucket.allow()
    clock.advance(2)
    assert bucket.tokens == 2
    assert bucket.allow() is True


def test_refill_never_exceeds_capacity():
    clock = FakeClock()
    bucket = TokenBucket(capacity=2, refill_rate=1, clock=clock)
    clock.advance(1000)
    assert bucket.tokens == 2


def test_wait_time_reports_the_real_delay():
    clock = FakeClock()
    bucket = TokenBucket(capacity=1, refill_rate=0.5, clock=clock)
    bucket.allow()
    assert bucket.wait_time() == pytest.approx(2.0)
    clock.advance(2)
    assert bucket.wait_time() == 0.0


def test_per_minute_converts_the_units_the_config_uses():
    bucket = TokenBucket.per_minute(60)
    assert bucket.refill_rate == pytest.approx(1.0)


# ------------------------------------------------------------------- quota


def test_the_daily_quota_is_a_hard_ceiling():
    quota = QuotaManager(daily_quota=2)
    assert [quota.allow() for _ in range(3)] == [True, True, False]
    assert quota.remaining == 0


def test_the_quota_rolls_over_at_midnight():
    day = ["2026-08-01T10:00:00"]

    class Stamp:
        def strftime(self, _fmt):
            return day[0][:10]

    quota = QuotaManager(daily_quota=1, clock=Stamp)
    assert quota.allow() is True
    assert quota.allow() is False
    day[0] = "2026-08-02T10:00:00"
    assert quota.allow() is True


# ------------------------------------------------------------- DOS detector


def test_normal_traffic_passes_the_detector():
    clock = FakeClock()
    dos = DosDetector(window_seconds=10, max_in_window=5, clock=clock)
    for _ in range(5):
        clock.advance(3)
        assert dos.allow() is True
    assert dos.locked is False


def test_a_runaway_loop_latches_the_breaker():
    dos = DosDetector(window_seconds=10, max_in_window=3, clock=FakeClock())
    results = [dos.allow() for _ in range(5)]
    assert results[:3] == [True, True, True]
    assert results[3] is False
    assert dos.locked is True


def test_the_breaker_stays_shut_until_a_human_resets_it():
    clock = FakeClock()
    dos = DosDetector(window_seconds=1, max_in_window=1, clock=clock)
    dos.allow()
    dos.allow()
    clock.advance(1000)
    assert dos.allow() is False       # time alone does not re-arm it
    dos.reset()
    assert dos.allow() is True


# --------------------------------------------------------------- gatekeeper


def limits(**overrides) -> dict:
    base = {
        "requests_per_minute": 600, "concurrent_max": 2, "retry_after_seconds": 0,
        "max_retries": 3, "queue_depth": 10, "daily_quota": 100,
        "dos_window_seconds": 10, "dos_max_in_window": 50,
    }
    return {**base, **overrides}


def test_a_healthy_call_passes_straight_through():
    gate = ApiGatekeeper(limits(), sleep=lambda _s: None)
    assert gate.execute(lambda value: value * 2, 21) == 42
    assert gate.status()["calls_made"] == 1


def test_a_transient_failure_is_retried_then_succeeds():
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise OSError("connection reset")
        return "ok"

    gate = ApiGatekeeper(limits(), sleep=lambda _s: None)
    assert gate.execute(flaky) == "ok"
    assert attempts["n"] == 3


def test_persistent_failure_raises_after_the_retry_budget():
    gate = ApiGatekeeper(limits(max_retries=2), sleep=lambda _s: None)
    with pytest.raises(RateLimited, match="failed 2 times"):
        gate.execute(lambda: (_ for _ in ()).throw(OSError("down")))
    assert gate.status()["calls_rejected"] == 1


def test_an_exhausted_quota_refuses_rather_than_risking_the_account():
    gate = ApiGatekeeper(limits(daily_quota=1), sleep=lambda _s: None)
    gate.execute(lambda: "first")
    with pytest.raises(RateLimited, match="Daily quota"):
        gate.execute(lambda: "second")


def test_a_tripped_breaker_refuses_and_says_why():
    gate = ApiGatekeeper(limits(dos_max_in_window=1), sleep=lambda _s: None)
    gate.execute(lambda: "first")
    with pytest.raises(RateLimited, match="DOS detector latched"):
        gate.execute(lambda: "second")
    # Latched: it stays shut for everything that follows, not just the offender.
    with pytest.raises(RateLimited, match="DOS detector latched"):
        gate.execute(lambda: "third")


def test_overflow_waits_for_a_token_instead_of_dropping_the_call():
    """Guidelines §5.3: a report that arrives late still scores; a dropped one does not."""
    slept: list[float] = []
    gate = ApiGatekeeper(limits(requests_per_minute=60, concurrent_max=1),
                         sleep=slept.append)
    for _ in range(4):
        gate.execute(lambda: "ok")
    assert gate.status()["calls_made"] == 4
    assert slept  # it waited rather than refusing


def test_status_is_observable():
    gate = ApiGatekeeper(limits(), sleep=lambda _s: None)
    status = gate.status()
    assert {"service", "calls_made", "quota_remaining", "dos"} <= set(status)
