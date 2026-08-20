"""The corner seal: how we lost a counted series 30-90, and what stops it.

All three thief sub-games we lost to imreeyal ended identically — thief on
(6,0), officer's walls on (5,0) and (6,1), concession under rule 47. From the
signed log of g02:

    step 12  [6,0]  W     barriers=[]              exits=2
    step 13  [6,0]  STAY  barriers=[]              exits=2
    step 14  [6,0]  STAY  barriers=[[5,0]]         exits=1
    step 15  [6,0]  STAY  barriers=[[5,0],[6,1]]   no legal move remains

Two walls out of fourteen, and five STAYs while the cage went up.

The solver scores against the walls that exist *now*, so on an open board the
far corner reports the full horizon precisely because it is far from the
officer. Every roomy cell reports the same capped number, the corner ties with
them, and the tie fell through to a positional score in which ``mobility_weight``
could never outvote distance. Exits now rank directly below proof, so the tie is
broken by how expensive the cell is to cage.
"""

import random

import pytest

from p2p_chase.domain.board import Board
from p2p_chase.strategy.base import candidate_moves
from p2p_chase.strategy.safe_thief import SafeThief

# The same fixture the rest of the safety suite uses. Reused rather than
# rebuilt: a second hand-rolled TurnContext is a second thing to get subtly
# wrong, and this one is already exercised by the tests that proved the solver.
from tests.unit.test_pursuit_safety import _context


@pytest.fixture
def board():
    return Board(7)


def _decide(board, thief, officer, barriers=(), seed=1):
    brain = SafeThief()
    brain._rng = random.Random(seed)
    context = _context(board, thief, officer, barriers=barriers)
    return brain._pick_move(candidate_moves(context), context)[1]


def _exits(board, cell, barriers=frozenset()):
    return len(board.neighbors(cell, set(barriers)))


# ------------------------------------------------------- the lost position


@pytest.mark.parametrize("officer", [(3, 1), (6, 4), (4, 3), (2, 2)])
def test_the_thief_does_not_step_into_the_corner_it_was_sealed_in(board, officer):
    """(6,1) -> (6,0) is the move that lost three sub-games."""
    assert _decide(board, (6, 1), officer) != (6, 0)


@pytest.mark.parametrize("officer", [(3, 0), (4, 1), (5, 3)])
def test_a_thief_already_in_the_corner_leaves_instead_of_standing_still(board, officer):
    """Step 13 of the real game: one wall down, four exits gone, and it stayed.

    STAY is a legal reply and the solver called it safe, because with the walls
    that existed it was. The officer was not finished building.
    """
    assert _decide(board, (6, 0), officer, barriers={(5, 0)}) != (6, 0)


def test_every_corner_is_refused_not_merely_the_one_we_lost_in(board):
    for corner, neighbour in (
        ((0, 0), (0, 1)), ((0, 6), (0, 5)), ((6, 0), (6, 1)), ((6, 6), (6, 5)),
    ):
        assert _decide(board, neighbour, (3, 3)) != corner


# ------------------------------------------------------------- the invariant


def test_among_equally_proven_moves_the_roomiest_wins(board):
    """Room ranks below proof and above preference — never the other way.

    Swept over random legal states, the rule is one-directional: the new
    ranking never chooses a cell with fewer exits than the old one did. That is
    the property, not the average.
    """
    rng = random.Random(7)
    cells = [(r, c) for r in range(7) for c in range(7)]
    checked = 0
    for _ in range(60):
        barriers = set(rng.sample(cells, rng.randint(0, 4)))
        free = [c for c in cells if c not in barriers]
        thief, officer = rng.sample(free, 2)
        context = _context(board, thief, officer, barriers=barriers)
        moves = candidate_moves(context)
        if not moves:
            continue
        brain = SafeThief()
        brain._rng = random.Random(1)
        brain._solved = {}
        table = brain._table(context, frozenset(barriers))
        threats = brain._threats(context)
        ranked = [(brain._safety(table, cell, threats, context), cell) for _, cell in moves]
        best = max(safety for safety, _ in ranked)
        if best[0] < table.depth:
            continue  # not saturated: survival decides, and should
        saturated = [cell for safety, cell in ranked if safety[0] >= table.depth]
        chosen = brain._pick_move(moves, context)[1]
        assert _exits(board, chosen, barriers) == max(
            _exits(board, cell, barriers) for cell in saturated
        )
        checked += 1
    assert checked, "swept no saturated positions — the invariant went untested"


def test_room_never_outranks_surviving_longer(board):
    """Below the horizon the question is which move loses slowest.

    Promoting room here would trade a cell that survives another ply for a
    roomier one that dies at once. Two tests caught that while this was written.
    """
    barriers = {(0, 1), (0, 3), (1, 3)}
    context = _context(Board(5), (0, 2), (1, 1), barriers=barriers)
    brain = SafeThief()
    brain._rng = random.Random(1)
    brain._solved = {}
    table = brain._table(context, frozenset(barriers))
    threats = brain._threats(context)
    for _, cell in candidate_moves(context):
        safety = brain._safety(table, cell, threats, context)
        assert safety[1] == 0, "room must be zero while the ply count is unsaturated"
