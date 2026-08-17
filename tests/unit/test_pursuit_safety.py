"""The thief's safety must be proved, not estimated.

We drew 47-47 with uoh-ay26 and read the six signed logs afterwards. Our thief
survived all three of its sub-games, and it survived by luck: it stood at
Chebyshev distance 1 from the officer on 16, 20 and 20 of 35 steps, every one of
them a diagonal adjacency. Neither side ever played STAY, so the parity of the
distance between them never changed and a shared cell stayed unreachable. One
STAY by the opponent flips that parity and every one of those adjacencies
becomes a capture chance.

The reason neither side ever stood still is not strategy. ``board.legal_moves``
returns steps, so no brain was ever offered the option, even though STAY is in
the signed move set and the state machine has always accepted it.

These tests pin the three failures behind that result: the missing STAY, the
trap a one-move veto cannot see, and the confidence threshold that switched the
old veto off exactly when the officer's position was least certain.
"""

import pytest

from p2p_chase.constants import MoveType, Role
from p2p_chase.domain.belief import BeliefGrid
from p2p_chase.domain.board import Board
from p2p_chase.strategy import pursuit
from p2p_chase.strategy.base import TurnContext, candidate_moves
from p2p_chase.strategy.safe_thief import SafeThief
from p2p_chase.strategy.thief_brain import OpenSpaceThief


class _State:
    """The slice of OwnGameState a thief brain actually reads."""

    def __init__(self, board, position, barriers=(), visited=(), can_stay=True):
        self.board = board
        self.position = position
        self.barriers = set(barriers)
        self.visited = set(visited)
        self.can_stay = can_stay
        self.role = Role.THIEF


def _context(board, position, officer, *, barriers=(), can_stay=True, spread=None):
    belief = BeliefGrid(board, smell_trust=4.0)
    if spread:
        belief.observe_region(list(spread), 0.99)
    else:
        belief.collapse_to(officer)
    return TurnContext(
        state=_State(board, position, barriers, can_stay=can_stay),
        belief=belief,
        trust=None,
        barriers_max=14,
        steps_remaining=20,
    )


@pytest.fixture
def board() -> Board:
    return Board(7)


# ------------------------------------------------------------------ STAY


def test_standing_still_is_offered_to_a_brain(board):
    """The option that was missing for the whole of the last series."""
    context = _context(board, (3, 3), (0, 0))
    assert (None, (3, 3)) in candidate_moves(context)


def test_standing_still_is_withheld_when_the_move_set_forbids_it(board):
    context = _context(board, (3, 3), (0, 0), can_stay=False)
    assert all(direction is not None for direction, _ in candidate_moves(context))


def test_a_deliberate_stay_is_not_recorded_as_a_fallback(board):
    """HOLD with no direction is also what a *failure* looks like, so the log has
    to tell a chosen STAY from a brain that ran out of options."""
    brain = SafeThief()
    decision = brain.decide(_context(board, (3, 3), (0, 0)))
    if decision.move_type is MoveType.HOLD:
        assert decision.target is not None
        assert decision.fallback is False


# ------------------------------------------------------------- the trap


# The position below was not invented to make a point. It was found by sweeping
# 4000 random boards for states the old thief loses and the new one survives:
# 53 of them exist, and they all look like this one -- diagonal contact, where
# every *step* is covered and only standing still is safe.
_TRAP_BARRIERS = {(0, 3)}
_TRAP_THIEF = (0, 2)
_TRAP_OFFICER = (1, 1)


def test_the_old_veto_finds_nothing_safe_and_then_ignores_itself(board):
    """The precise mechanism of the loss, pinned so it cannot come back.

    ``_safe_moves`` correctly reports that *both* steps finish within reach of
    the officer, and then ``_safe_moves(...) or moves`` throws that away and
    scores the unsafe moves anyway. Vetoing everything and vetoing nothing are
    the same thing here.
    """
    context = _context(board, _TRAP_THIEF, _TRAP_OFFICER, barriers=_TRAP_BARRIERS)
    legal = board.legal_moves(_TRAP_THIEF, _TRAP_BARRIERS)

    assert OpenSpaceThief()._safe_moves(legal, context) == []

    _, target = OpenSpaceThief()._pick_move(legal, context)
    table = pursuit.solve(board, _TRAP_BARRIERS, 12)
    assert table.plies_after_move(target, _TRAP_OFFICER) == 0


def test_the_safe_thief_stands_still_and_lives(board):
    """Same position, and the option the old thief was never offered."""
    context = _context(board, _TRAP_THIEF, _TRAP_OFFICER, barriers=_TRAP_BARRIERS)
    table = pursuit.solve(board, _TRAP_BARRIERS, 12)

    direction, target = SafeThief()._pick_move(candidate_moves(context), context)

    assert direction is None and target == _TRAP_THIEF
    assert table.plies_after_move(target, _TRAP_OFFICER) == table.depth


def test_a_losing_position_still_picks_the_slowest_loss(board):
    """When nothing is safe the criterion is kept, not abandoned."""
    barriers = {(0, 1), (0, 3), (1, 3)}
    context = _context(board, _TRAP_THIEF, _TRAP_OFFICER, barriers=barriers)
    table = pursuit.solve(board, barriers, 12)

    _, target = SafeThief()._pick_move(candidate_moves(context), context)

    best = max(
        table.plies_after_move(cell, _TRAP_OFFICER)
        for _, cell in candidate_moves(context)
    )
    assert table.plies_after_move(target, _TRAP_OFFICER) == best


# ------------------------------------------------- uncertainty and parity


def test_safety_does_not_switch_off_when_the_belief_is_vague(board):
    """The old veto needed 0.5 mass on one cell or it allowed everything.

    A diffuse belief is a reason to avoid *more* of the board, not less, so the
    threat set widens and every candidate must survive all of it.
    """
    spread = [(2, 1), (1, 2), (4, 5), (5, 4)]
    context = _context(board, (3, 3), (2, 1), spread=spread)
    assert context.belief.probability(context.belief.most_likely()) < 0.5

    brain = SafeThief()
    assert len(brain._threats(context)) > 1

    _, target = brain._pick_move(candidate_moves(context), context)
    table = pursuit.solve(board, set(), 12)
    # Safe against every officer position still in play, not merely the hottest.
    assert min(table.plies_after_move(target, cell) for cell in spread) == table.depth


def test_being_surrounded_is_not_answered_by_standing_still(board):
    """With the officer possibly on all four sides, nothing is guaranteed — and
    STAY is the one certain loss, because every one of those officers steps onto
    us. The worst case ties at zero, so the tie-breakers have to carry it."""
    spread = [(3, 2), (3, 4), (2, 3), (4, 3)]
    context = _context(board, (3, 3), (3, 2), spread=spread)

    direction, _ = SafeThief()._pick_move(candidate_moves(context), context)

    assert direction is not None


def test_a_thief_at_diagonal_contact_still_has_a_proven_reply(board):
    """The position we spent 20 steps a sub-game in, now answered on purpose."""
    context = _context(board, (3, 3), (4, 4))
    table = pursuit.solve(board, set(), 12)

    _, target = SafeThief()._pick_move(candidate_moves(context), context)

    assert table.plies_after_move(target, (4, 4)) == table.depth
    assert target != (4, 4)


def test_the_officer_cannot_force_a_capture_on_an_open_board(board):
    """Why a draw is the floor and not the ceiling: with STAY available there is
    no forced capture, so a proved-safe thief simply cannot be taken."""
    table = pursuit.solve(board, set(), 12)
    for officer in [(0, 0), (3, 2), (2, 2), (6, 6)]:
        assert table.survivable_plies((3, 3), officer) == table.depth


# ----------------------------------------------------------- determinism


def test_equally_safe_choices_are_not_always_the_same_one(board):
    """Two sub-games of the last series were byte-identical. Randomising among
    provably-equal options costs no safety and denies an opponent the replay."""
    import random

    seen = set()
    for seed in range(40):
        brain = SafeThief(rng=random.Random(seed))
        context = _context(board, (3, 3), (0, 0))
        seen.add(brain._pick_move(candidate_moves(context), context)[1])
    assert len(seen) > 1
