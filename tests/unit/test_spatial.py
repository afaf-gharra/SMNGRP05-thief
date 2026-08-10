"""Spatial analysis and barrier planning: the geometry the tactics rest on."""

import pytest

from p2p_chase.strategy import reachability
from p2p_chase.strategy.barriers import plan_barrier, should_spend

# ------------------------------------------------------------- reachability


def test_distance_map_reaches_the_whole_open_board(board):
    assert len(reachability.distance_map(board, (0, 0))) == 49


def test_distance_map_measures_around_walls(board):
    wall = {(0, 1), (1, 1), (2, 1)}
    assert reachability.distance_map(board, (0, 0), wall)[(0, 2)] == 8


def test_region_size_halves_across_a_full_wall(board):
    wall = {(3, col) for col in range(7)}
    assert reachability.region_size(board, (0, 0), wall) == 21


def test_expected_region_size_is_belief_weighted(board):
    """An asymmetric wall: a 7-cell pocket in the corner, 41 cells outside it."""
    wall = {(1, 0), (1, 1), (1, 2), (0, 3), (1, 3)}
    pocket = reachability.expected_region_size(board, [((0, 0), 1.0)], wall)
    outside = reachability.expected_region_size(board, [((6, 6), 1.0)], wall)
    split = reachability.expected_region_size(
        board, [((0, 0), 0.5), ((6, 6), 0.5)], wall
    )
    assert pocket == 3
    assert outside == 41
    assert split == pytest.approx((pocket + outside) / 2)


def test_expected_region_size_of_nothing_is_the_whole_board(board):
    assert reachability.expected_region_size(board, []) == 49


def test_expected_distance_charges_for_unreachable_cells(board):
    distances = reachability.distance_map(board, (0, 0), {(0, 1), (1, 0), (1, 1)})
    assert reachability.expected_distance(distances, [((6, 6), 1.0)], 99) == 99


def test_exits_counts_ways_out(board):
    assert reachability.exits(board, (0, 0)) == 2
    assert reachability.exits(board, (3, 3)) == 4
    assert reachability.exits(board, (0, 0), {(0, 1)}) == 1


def test_a_corridor_cell_is_a_cut_vertex(board):
    """Sealing the single gap in a wall severs the board — the best wall there is."""
    wall = {(3, col) for col in range(7) if col != 3}
    assert reachability.is_cut_vertex(board, (3, 3), wall) is True


def test_an_open_cell_is_not_a_cut_vertex(board):
    assert reachability.is_cut_vertex(board, (3, 3)) is False


def test_a_dead_end_is_not_a_cut_vertex(board):
    assert reachability.is_cut_vertex(board, (0, 0)) is False


def test_frontier_cells_are_the_officers_barrier_palette(board):
    assert reachability.frontier_cells(board, (3, 3), radius=1) == {
        (2, 3), (4, 3), (3, 2), (3, 4)
    }


# ---------------------------------------------------------- barrier planner


def test_a_wall_that_would_cut_us_off_from_the_thief_is_refused(board):
    """The veto that matters: never build the thief's fortress for it.

    The officer stands north of a wall whose single gap is the only way to the
    thief. Sealing that gap is enormously valuable on paper — it removes most of
    the board from the thief's region — and completely self-defeating, because
    the officer would be left on the wrong side. It must be refused.
    """
    wall = {(3, col) for col in range(7) if col != 3}
    plan = plan_barrier(board, (2, 3), wall, [((6, 6), 1.0)])
    assert plan is None or plan.cell != (3, 3)


def test_the_planner_prefers_a_cut_vertex(board):
    """One cell spent, a corridor severed.

    Note what the immediate cell count says here: *nothing*. The officer is
    standing in the gap, so its own body is already containing the thief and
    sealing the cell removes no reachable cells today. The wall is still by far
    the best move available, because it makes that containment permanent and
    frees the officer to walk away and hunt. A planner that priced walls purely
    on cells-removed-right-now would miss it entirely — which is exactly why the
    valuation is structural.
    """
    wall = {(3, col) for col in range(7) if col != 3}
    plan = plan_barrier(board, (4, 3), wall, [((4, 5), 1.0)])  # adjacent to the gap
    assert plan is not None
    assert plan.cell == (3, 3)
    assert plan.cells_removed == 0
    assert plan.value > 6.0        # dominated by the cut bonus, not by cells


def test_sealing_a_probably_occupied_cell_scores_highly(board):
    """Rule 46 makes a wall on the thief's cell a capture, so it must dominate."""
    plan = plan_barrier(board, (3, 3), set(), [((3, 4), 0.9)])
    assert plan is not None
    assert plan.cell == (3, 4)


def test_the_planner_returns_nothing_without_a_belief(board):
    assert plan_barrier(board, (3, 3), set(), []) is None


def test_walls_are_not_spent_once_the_quota_is_gone(board):
    plan = plan_barrier(board, (3, 3), set(), [((6, 6), 1.0)])
    assert should_spend(
        plan=plan, barriers_left=0, steps_remaining=10, total_steps=35,
        expected_distance=6, board_size=7, reserve=3, threshold=3.0,
    ) is False


def test_a_wall_is_only_worth_a_turn_when_it_can_reach_the_thief(board):
    """Barriers go beside the officer, so a distant thief cannot be walled at all.

    This assertion is deliberately the reverse of what it used to be. The earlier
    rule built while the thief was far and refused while it was close, and in a
    live series that produced five barriers fencing an empty board edge while the
    pursuit distance doubled and the thief escaped.
    """
    plan = plan_barrier(board, (3, 3), set(), [((3, 5), 1.0)])
    common = {"barriers_left": 10, "steps_remaining": 10, "total_steps": 35,
              "board_size": 7, "reserve": 3, "threshold": 0.5}
    assert should_spend(plan=plan, expected_distance=1.0, **common) is True
    assert should_spend(plan=plan, expected_distance=6.0, **common) is False

