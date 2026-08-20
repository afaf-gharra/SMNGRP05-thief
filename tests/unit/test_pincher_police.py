"""``PincherPolice`` — the instrument our benchmark was missing.

The arena certified the corner-seal failure at "one sub-game in three hundred"
while the live rate against imreeyal was three in three. The estimate was not
dishonest, it was taken with an instrument that shared the blind spot: no
officer in ``scripts/arena.py`` ever spent a wall to shrink a cornered thief, so
the arena could not produce the position the estimate was about.

This class reproduces that tactic from six signed sub-games. It is a measuring
device first. It was also evaluated as a replacement for our own officer and
**did not earn it** — it fails to beat ``ArchitectPolice`` consistently and
regresses against ``GreedyThief`` — so ``police_class`` is unchanged and these
tests pin it as a benchmark opponent rather than as shipped strategy.
"""

import random

import pytest

from p2p_chase.constants import MoveType
from p2p_chase.domain.board import Board
from p2p_chase.strategy.pincher_police import PincherPolice
from tests.unit.test_pursuit_safety import _State


@pytest.fixture
def board():
    return Board(7)


def _context(board, officer, thief, barriers=(), my_barriers=0):
    """A turn where the officer believes the thief is exactly on ``thief``."""
    from p2p_chase.domain.belief import BeliefGrid
    from p2p_chase.strategy.base import TurnContext

    belief = BeliefGrid(board, smell_trust=4.0)
    belief.collapse_to(thief)
    state = _State(board, officer, barriers)
    state.my_barriers = my_barriers
    # ``_State`` carries the slice a *thief* brain reads; the officer's barrier
    # planner also asks how far into the sub-game we are, to decide whether a
    # wall is still worth a turn.
    state.step_number = 1
    return TurnContext(
        state=state, belief=belief, trust=None, barriers_max=14, steps_remaining=20,
    )


def _brain():
    brain = PincherPolice(rng=random.Random(1))
    return brain


def _wall_for(context):
    brain = _brain()
    return brain._wall(context, context.belief.top_cells(8))


# ------------------------------------------------------------ it does pinch


def test_it_spends_a_wall_on_an_exit_of_a_cornered_thief(board):
    """The live position: thief in the corner, officer beside its escape.

    (6,0) has exits (5,0) and (6,1). Standing on (5,1) the officer can legally
    build on either. ArchitectPolice declines both unless the structural score
    clears wall_threshold, which is why it spent zero of fourteen barriers
    across three live windows.
    """
    plan = _wall_for(_context(board, officer=(5, 1), thief=(6, 0)))
    assert plan is not None
    assert plan.cell in {(5, 0), (6, 1)}


def test_an_open_thief_is_not_worth_a_wall(board):
    """A cell with four exits cannot be caged cheaply, so the pinch declines.

    This is also why the fixed thief starves it: staying on open ground means
    the officer never gets a cell worth spending on.
    """
    brain = _brain()
    context = _context(board, officer=(3, 2), thief=(3, 3))
    assert brain._pinch(context, context.belief.top_cells(8)) is None


# ---------------------------------------------------------- and it stays safe


def test_the_endgame_reserve_is_never_raided(board):
    """barrier_reserve exists so the last walls are available for the squeeze."""
    context = _context(board, officer=(5, 1), thief=(6, 0), my_barriers=12)
    brain = _brain()
    assert brain._pinch(context, context.belief.top_cells(8)) is None


def test_a_pinch_is_still_subject_to_every_veto_a_structural_wall_is(board):
    """Only the *reason* for building differs, never the safety checks.

    Routed through ``barriers.evaluate_wall`` so ``own_region_floor`` and the
    "never enlarge the thief's region" rule apply unchanged. Asserted by driving
    the floor to 1.0, which no wall can satisfy.
    """
    brain = PincherPolice(rng=random.Random(1), tuning={"own_region_floor": 1.0})
    context = _context(board, officer=(5, 1), thief=(6, 0))
    assert brain._pinch(context, context.belief.top_cells(8)) is None


def test_it_never_builds_less_than_the_officer_it_extends(board):
    """The inherited planner is given a second reason to fire, not replaced.

    Where no pinch is available the decision falls through to ArchitectPolice
    untouched, so this class cannot make the officer *more* passive than the one
    it inherits from — which was the whole complaint against the original.
    """
    from p2p_chase.strategy.police_brain import ArchitectPolice

    context = _context(board, officer=(3, 2), thief=(3, 3))
    cells = context.belief.top_cells(8)
    inherited = ArchitectPolice(rng=random.Random(1))._wall(context, cells)
    assert (_wall_for(context) is None) == (inherited is None)


def test_the_decision_is_a_barrier_move(board):
    """End to end: the brain actually emits BARRIER, not merely a plan."""
    decision = _brain().decide(_context(board, officer=(5, 1), thief=(6, 0)))
    assert decision.move_type is MoveType.BARRIER
    assert decision.target in {(5, 0), (6, 1)}
