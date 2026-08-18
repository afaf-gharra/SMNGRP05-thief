"""Deadlines, the watchdog and the orchestrator: staying alive when things break.

None of these decide a move. They decide whether a broken opponent, a frozen loop
or a dead socket costs one sub-game or the whole series.
"""

import json
from pathlib import Path

from p2p_chase.constants import Role
from p2p_chase.exceptions import TransportError
from p2p_chase.peer.deadline import Deadline, DeadlineTracker
from p2p_chase.peer.orchestrator import Orchestrator
from p2p_chase.peer.watchdog import Watchdog

# ------------------------------------------------------------------- deadline


def test_a_deadline_expires_and_is_counted():
    tracker = DeadlineTracker(default_budget=0.0)
    deadline = tracker.start("opponent_turn")
    assert deadline.expired is True
    assert tracker.record(deadline) is True
    assert tracker.summary()["total_expiries"] == 1


def test_a_met_deadline_is_counted_separately():
    tracker = DeadlineTracker(default_budget=60)
    deadline = tracker.start("opponent_turn")
    assert deadline.expired is False
    assert tracker.record(deadline) is False
    assert tracker.summary()["completions"] == {"opponent_turn": 1}


def test_resetting_a_deadline_restarts_the_budget():
    deadline = Deadline(budget_seconds=0.0)
    assert deadline.expired is True
    deadline.budget_seconds = 60
    deadline.reset()
    assert deadline.expired is False
    assert deadline.remaining > 0


# ------------------------------------------------------------------- watchdog


class Ticker:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_a_beating_loop_is_left_alone(tmp_path):
    clock = Ticker()
    dog = Watchdog(timeout_seconds=10, state_dir=tmp_path, clock=clock)
    clock.now = 5
    assert dog.check() is False
    dog.beat()
    clock.now = 12
    assert dog.check() is False
    assert dog.beats == 1


def test_a_frozen_loop_triggers_a_controlled_shutdown(tmp_path):
    clock = Ticker()
    fired: list[bool] = []
    dog = Watchdog(timeout_seconds=10, state_dir=tmp_path, clock=clock,
                   on_freeze=lambda: fired.append(True))
    dog.bind(lambda: {"phase": "COMPUTING_MOVE", "step": 7})
    clock.now = 30
    assert dog.check() is True
    assert fired == [True]
    saved = list(Path(tmp_path).glob("watchdog_*.json"))
    assert saved, "the watchdog must persist state so the match can still be reported"
    assert json.loads(saved[0].read_text(encoding="utf-8"))["step"] == 7


def test_the_watchdog_stays_triggered_once_it_fires(tmp_path):
    clock = Ticker()
    dog = Watchdog(timeout_seconds=1, state_dir=tmp_path, clock=clock)
    clock.now = 10
    dog.check()
    assert dog.check() is True
    assert dog.summary()["triggered"] is True


def test_a_failing_snapshot_does_not_mask_the_freeze(tmp_path):
    dog = Watchdog(timeout_seconds=1, state_dir=tmp_path, clock=Ticker())
    dog.bind(lambda: (_ for _ in ()).throw(RuntimeError("state is gone")))
    assert dog.persist() is None


def test_persist_without_a_snapshot_is_a_no_op(tmp_path):
    assert Watchdog(state_dir=tmp_path).persist() is None


def test_start_and_stop_are_idempotent(tmp_path):
    dog = Watchdog(timeout_seconds=60, state_dir=tmp_path, poll_seconds=0.01)
    dog.start()
    dog.start()
    dog.stop()
    dog.stop()


# --------------------------------------------------------------- orchestrator


def test_a_broken_transport_becomes_a_scored_technical_loss(sdk):
    """A crash must not lose the series: 0-0 is a result, silence is not."""

    class DeadTransport:
        def exchange_agreement(self, _signed, expect_sub_game=None):
            raise TransportError("opponent never came online")

        def drain_inboxes(self):
            pass

    sdk.config.override("league.num_games", 1)
    series = Orchestrator(sdk.config, DeadTransport()).play_series(Role.POLICE)
    assert len(series.summaries) == 1
    assert series.summaries[0]["result"] == "timeout"
    assert "opponent never came online" in series.summaries[0]["error"]


def test_the_orchestrator_snapshot_is_safe_before_a_sub_game(sdk):
    orchestrator = Orchestrator(sdk.config, object())
    assert "no sub-game" in orchestrator._snapshot()["status"]
