"""Board geometry, including the graph facts the strategies actually rely on."""

import pytest

from p2p_chase.constants import Direction
from p2p_chase.domain.board import Board


def test_rejects_a_degenerate_board():
    with pytest.raises(ValueError, match="at least 2"):
        Board(1)


def test_default_move_set_is_the_four_orthogonals(board):
    assert set(board.moves) == {Direction.N, Direction.S, Direction.E, Direction.W}
    assert board.diagonal is False


def test_distance_is_manhattan_without_diagonals(board):
    assert board.distance((0, 0), (2, 3)) == 5


def test_distance_is_chebyshev_when_diagonals_are_negotiated():
    king = Board(7, moves=list(Direction))
    assert king.diagonal is True
    assert king.distance((0, 0), (2, 3)) == 3


def test_steps_off_the_board_are_illegal(board):
    assert board.step((0, 0), Direction.N) is None
    assert board.step((0, 0), Direction.S) == (1, 0)


def test_a_direction_outside_the_move_set_is_illegal(board):
    assert board.step((3, 3), Direction.NE) is None


def test_barriers_block_movement(board):
    assert board.step((3, 3), Direction.E, {(3, 4)}) is None


def test_legal_moves_shrink_in_a_corner(board):
    assert len(board.legal_moves((0, 0))) == 2
    assert len(board.legal_moves((3, 3))) == 4


def test_reachable_covers_an_open_board(board):
    assert len(board.reachable((0, 0))) == 49


def test_reachable_respects_a_full_wall(board):
    wall = {(3, col) for col in range(7)}
    assert len(board.reachable((0, 0), wall)) == 21


def test_reachable_honours_a_depth_limit(board):
    assert board.reachable((3, 3), limit=1) == {(3, 3), (2, 3), (4, 3), (3, 2), (3, 4)}


def test_shortest_path_walks_around_a_wall(board):
    wall = {(0, 1), (1, 1), (2, 1)}
    assert board.distance((0, 0), (0, 2)) == 2          # naive
    assert board.shortest_path_length((0, 0), (0, 2), wall) == 8  # around the wall


def test_shortest_path_is_none_when_cut_off(board):
    wall = {(0, 1), (1, 0), (1, 1)}
    assert board.shortest_path_length((0, 0), (5, 5), wall) is None


def test_shortest_path_to_self_is_zero(board):
    assert board.shortest_path_length((2, 2), (2, 2)) == 0
