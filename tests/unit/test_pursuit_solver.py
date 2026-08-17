"""The solver is load-bearing, so it is checked against the definition.

Every safety claim the thief makes now rests on :mod:`pursuit`. A bitmask
backward induction is fast because it does a whole ply in a handful of integer
operations, and that is exactly what makes it easy to get quietly wrong — an
off-by-one in a shift is not a crash, it is a thief that believes it is safe.

So these tests do not check the implementation against itself. They check it
against a naive recursive definition of the game, exhaustively, over every
(thief, officer, depth) triple on small boards. One real bug was caught this
way: where STAY is not in the move set, an officer standing on the thief has to
step off, and every one of those steps passed the subset test, so a capture that
had already happened was scored as survival.
"""

import itertools
import random
from functools import cache

import pytest

from p2p_chase.domain.board import Board
from p2p_chase.strategy import pursuit


def _reference(board: Board, blocked: frozenset, stay: bool):
    """The rules, written the obvious way and too slow to ship."""

    def options(cell):
        return ([cell] if stay else []) + board.neighbors(cell, blocked)

    @cache
    def thief_to_move(thief, officer, plies):
        if thief == officer:
            return False
        # Rule 47: a thief with no *step* is captured by enclosure, and standing
        # still does not save it. Only directional moves count here.
        if not board.neighbors(thief, blocked):
            return False
        if plies <= 0:
            return True
        return any(
            target != officer and officer_to_move(target, officer, plies)
            for target in options(thief)
        )

    @cache
    def officer_to_move(thief, officer, plies):
        if thief == officer:
            return False
        if not board.neighbors(thief, blocked):
            return False
        return all(
            reply != thief and thief_to_move(thief, reply, plies - 1)
            for reply in options(officer)
        )

    return thief_to_move, officer_to_move


def _cases():
    fixed = [
        (3, frozenset(), True, 4),
        (3, frozenset({(1, 1)}), True, 4),
        (3, frozenset(), False, 4),
        (3, frozenset({(0, 1)}), False, 4),
        (4, frozenset(), True, 3),
        (4, frozenset(), False, 3),
        (4, frozenset({(0, 1), (1, 1), (2, 1)}), True, 3),
        # A one-cell pocket: the enclosure rule, which STAY must not rescue.
        (3, frozenset({(0, 1), (1, 0)}), True, 4),
        (4, frozenset({(0, 1), (1, 0), (3, 2), (2, 3)}), True, 3),
    ]
    rng = random.Random(11)
    for _ in range(8):
        size = rng.choice([3, 4])
        walls = frozenset(
            (rng.randrange(size), rng.randrange(size)) for _ in range(rng.randint(1, 4))
        )
        fixed.append((size, walls, rng.choice([True, False]), 3))
    return fixed


@pytest.mark.parametrize(("size", "blocked", "stay", "horizon"), _cases())
def test_both_layers_agree_with_an_exhaustive_reference(size, blocked, stay, horizon):
    board = Board(size)
    table = pursuit.solve(board, blocked, horizon, stay_allowed=stay)
    thief_to_move, officer_to_move = _reference(board, blocked, stay)
    cells = [
        (row, col)
        for row in range(size)
        for col in range(size)
        if (row, col) not in blocked
    ]

    for thief, officer in itertools.product(cells, cells):
        for plies in range(1, horizon + 1):
            assert table.survives(thief, officer, plies) == thief_to_move(
                thief, officer, plies
            ), f"thief-to-move {thief} {officer} {plies}"
            assert table.survives_after_move(thief, officer, plies) == officer_to_move(
                thief, officer, plies
            ), f"officer-to-move {thief} {officer} {plies}"


def test_sharing_a_cell_is_never_survivable():
    board = Board(5)
    table = pursuit.solve(board, set(), 4)
    for row in range(5):
        for col in range(5):
            assert not table.survives((row, col), (row, col), 1)
            assert table.survivable_plies((row, col), (row, col)) == 0


def test_a_walled_off_thief_is_safe_forever():
    """Two components mean the officer can never arrive, whatever it does."""
    board = Board(7)
    walls = {(0, 2), (1, 2), (2, 0), (2, 1), (2, 2)}
    table = pursuit.solve(board, walls, 12)
    assert table.survivable_plies((0, 0), (6, 6)) == table.depth


def test_a_sealed_thief_survives_nothing():
    board = Board(7)
    walls = {(0, 1), (1, 0)}
    table = pursuit.solve(board, walls, 6)
    # (0,0) has no exits at all: not a trap, a completed capture.
    assert table.survivable_plies((0, 0), (3, 3)) == 0


def test_the_open_board_has_no_forced_capture():
    """The reason a draw is the floor: with STAY available the thief always has
    an answer, so no officer can force a capture and no proved-safe thief loses."""
    board = Board(7)
    table = pursuit.solve(board, set(), 12)
    cells = [(row, col) for row in range(7) for col in range(7)]
    for thief, officer in itertools.product(cells, cells):
        if thief != officer:
            assert table.survivable_plies(thief, officer) == table.depth


def test_a_full_size_solve_is_fast_enough_to_run_every_turn():
    import time

    board = Board(7)
    started = time.perf_counter()
    pursuit.solve(board, {(3, 3), (2, 2)}, pursuit.DEFAULT_HORIZON)
    assert time.perf_counter() - started < 1.0
