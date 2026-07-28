"""Offline benchmark harness: play many matches, print the numbers.

Strategy claims are worthless without a denominator. This script plays a fixed
number of full sub-games — real brains, real belief, real scent, real barrier
budget — across a spread of seeds and reports capture rate, mean length and wall
usage. It is what turns "the architect officer feels better" into a table in
``docs/RESEARCH-REPORT.md``.

The transport is a direct in-process shuttle rather than MCP: the protocol layer
is exercised by the integration test, and here we want a thousand matches, not a
thousand handshakes.

    uv run python scripts/arena.py --matches 40
    uv run python scripts/arena.py --matches 40 --cop greedy --thief openspace
"""

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from p2p_chase.constants import MoveType, Outcome, Role  # noqa: E402
from p2p_chase.domain.belief import BeliefGrid  # noqa: E402
from p2p_chase.domain.own_state import OwnGameState  # noqa: E402
from p2p_chase.domain.rules import GameRules  # noqa: E402
from p2p_chase.domain.smell import SmellField  # noqa: E402
from p2p_chase.domain.trust import TrustEstimator  # noqa: E402
from p2p_chase.strategy.base import TurnContext  # noqa: E402
from p2p_chase.strategy.baselines import GreedyPolice, GreedyThief  # noqa: E402
from p2p_chase.strategy.police_brain import ArchitectPolice  # noqa: E402
from p2p_chase.strategy.thief_brain import OpenSpaceThief  # noqa: E402

BRAINS = {
    "architect": ArchitectPolice, "greedy": GreedyPolice,
    "openspace": OpenSpaceThief, "greedythief": GreedyThief,
}

TERMS = {
    "board_size": 7, "thief_start": (3, 3), "cop_start": (0, 0),
    "survival_threshold": 35, "barriers_max": 14,
    "grid_size": 5, "decay": 0.10, "emit": 0.9,
}


def sample_starts(seed: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """Draw a distinct start pair for this seed.

    Both strategies are deterministic, so a fixed opening would make every match
    in a run byte-identical and any "capture rate" meaningless. Start positions
    are a negotiated term anyway, so sampling them is both honest and realistic:
    it measures the strategy across the openings an opponent might actually
    propose, rather than one lucky board.
    """
    if seed == 0:
        return TERMS["thief_start"], TERMS["cop_start"]
    rng = random.Random(seed * 104729)
    size = TERMS["board_size"]
    while True:
        thief = (rng.randrange(size), rng.randrange(size))
        cop = (rng.randrange(size), rng.randrange(size))
        # A start pair already in contact would decide the match before move one.
        if abs(thief[0] - cop[0]) + abs(thief[1] - cop[1]) >= 3:
            return thief, cop


class Side:
    """One agent's private world inside the benchmark."""

    def __init__(self, role: Role, brain_cls, seed: int, tuning: dict | None = None,
                 start: tuple[int, int] | None = None) -> None:
        start = start or (TERMS["thief_start"] if role is Role.THIEF else TERMS["cop_start"])
        self.role = role
        self.state = OwnGameState(role, start, TERMS["board_size"], ["N", "S", "E", "W", "STAY"])
        self.state.set_quota(TERMS["barriers_max"])
        self.belief = BeliefGrid(self.state.board, smell_trust=4.0)
        self.scent_in = self._field()
        self.scent_out = self._field()
        self.trust = TrustEstimator()
        self.brain = brain_cls(rng=random.Random(seed), talker=None, tuning=tuning or {})

    @staticmethod
    def _field() -> SmellField:
        return SmellField(TERMS["board_size"], TERMS["grid_size"], TERMS["decay"], 0.0)

    def context(self, steps_remaining: int) -> TurnContext:
        return TurnContext(
            state=self.state, belief=self.belief, trust=self.trust,
            barriers_max=TERMS["barriers_max"], steps_remaining=steps_remaining,
        )


def play(cop_cls, thief_cls, seed: int, cop_tune=None, thief_tune=None) -> dict:
    """One sub-game. Returns the outcome and a few diagnostics."""
    thief_start, cop_start = sample_starts(seed)
    cop = Side(Role.POLICE, cop_cls, seed, cop_tune, cop_start)
    thief = Side(Role.THIEF, thief_cls, seed + 7919, thief_tune, thief_start)
    rules = GameRules(TERMS["survival_threshold"])

    for turn in range(TERMS["survival_threshold"] * 2):
        mover, other = (thief, cop) if turn % 2 == 0 else (cop, thief)
        if mover.role is Role.THIEF and mover.state.is_immobilised():
            return _done(Outcome.CAPTURE.value, cop, thief, "enclosure")

        decision = mover.brain.decide(mover.context(
            max(0, TERMS["survival_threshold"] - thief.state.step_number)
        ))
        if not mover.state.apply_move(decision.move_type, decision.direction, TERMS["barriers_max"]):
            mover.state.apply_move(MoveType.HOLD, None)

        if wall := mover.state.last_barrier():
            other.state.note_barrier(wall)
            if mover.role is Role.POLICE and tuple(wall) == tuple(thief.state.position):
                return _done(Outcome.CAPTURE.value, cop, thief, "sealed on the thief")

        if (
            mover.role is Role.POLICE
            and decision.claims_capture
            and tuple(cop.state.position) == tuple(thief.state.position)
        ):
            return _done(Outcome.CAPTURE.value, cop, thief, "stepped onto the thief")

        _exchange(mover, other, decision)
        if mover.role is Role.THIEF and rules.thief_result(mover.state):
            return _done(Outcome.SURVIVAL.value, cop, thief, "outlasted the clock")
    return _done(Outcome.SURVIVAL.value, cop, thief, "loop ceiling")


def _exchange(mover: Side, other: Side, decision) -> None:
    """Deposit the mover's scent and let the other side observe it."""
    mover.scent_out.deposit(mover.state.position, TERMS["emit"])
    mover.scent_out.decay_all()
    grid = mover.scent_out.snapshot()
    other.belief.predict(other.state.barriers, stay_allowed=True)
    other.belief.observe_smell(grid)
    other.scent_in.absorb(grid)
    other.scent_in.decay_all()
    other.belief.exclude_all({other.state.position, *other.state.barriers})
    if mover.role is Role.POLICE and decision.claims_capture:
        other.belief.collapse_to(mover.state.position)


def _done(result: str, cop: Side, thief: Side, how: str) -> dict:
    return {
        "result": result, "how": how, "steps": thief.state.step_number,
        "barriers": cop.state.my_barriers, "thief_cells": thief.state.unique_cells,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark cop/thief strategies head to head")
    parser.add_argument("--matches", type=int, default=40)
    parser.add_argument("--cop", default="architect", choices=["architect", "greedy"])
    parser.add_argument("--thief", default="openspace", choices=["openspace", "greedythief"])
    parser.add_argument("--json", action="store_true", help="emit machine-readable results")
    parser.add_argument("--cop-tune", default="{}", help="JSON overrides for the officer's weights")
    parser.add_argument("--thief-tune", default="{}", help="JSON overrides for the thief's weights")
    args = parser.parse_args()

    cop_tune, thief_tune = json.loads(args.cop_tune), json.loads(args.thief_tune)
    games = [
        play(BRAINS[args.cop], BRAINS[args.thief], seed, cop_tune, thief_tune)
        for seed in range(args.matches)
    ]
    captures = [g for g in games if g["result"] == Outcome.CAPTURE.value]
    report = {
        "cop": args.cop, "thief": args.thief, "matches": len(games),
        "capture_rate": round(len(captures) / len(games), 3),
        "mean_steps": round(statistics.fmean(g["steps"] for g in games), 1),
        "mean_capture_steps": round(statistics.fmean(g["steps"] for g in captures), 1) if captures else None,
        "mean_barriers": round(statistics.fmean(g["barriers"] for g in games), 1),
        "cop_points": sum(20 if g["result"] == "capture" else 5 for g in games),
        "thief_points": sum(5 if g["result"] == "capture" else 10 for g in games),
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{args.cop:>10} vs {args.thief:<12} "
              f"capture {report['capture_rate']:.0%}  "
              f"steps~{report['mean_steps']}  walls~{report['mean_barriers']}  "
              f"points {report['cop_points']}:{report['thief_points']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
