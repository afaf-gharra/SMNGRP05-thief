"""The graded seam: reachability analysis, barrier planning, and both brains."""

import random

import pytest

from p2p_chase.constants import MoveType, Role
from p2p_chase.domain.belief import BeliefGrid
from p2p_chase.domain.own_state import OwnGameState
from p2p_chase.domain.trust import TrustEstimator
from p2p_chase.exceptions import ConfigError
from p2p_chase.strategy import reachability
from p2p_chase.strategy.barriers import plan_barrier, should_spend
from p2p_chase.strategy.base import BrainBase, TurnContext
from p2p_chase.strategy.factory import load_brain_cls, resolve_brain, resolve_brain_cls
from p2p_chase.strategy.police_brain import ArchitectPolice
from p2p_chase.strategy.thief_brain import OpenSpaceThief

MOVES = ["N", "S", "E", "W", "STAY"]


def context(role, start, barriers=(), threat=None, steps_remaining=20, tuning=None):
    state = OwnGameState(role, start, 7, MOVES)
    state.set_quota(14)
    for cell in barriers:
        state.note_barrier(cell)
    belief = BeliefGrid(state.board)
    if threat is not None:
        belief.collapse_to(threat)
    return TurnContext(
        state=state, belief=belief, trust=TrustEstimator(board_cells=49),
        barriers_max=14, steps_remaining=steps_remaining, tuning=tuning or {},
    )


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


def test_closing_in_raises_the_bar_for_stopping_to_build(board):
    """Within striking distance a turn spent building is a turn not spent closing."""
    plan = plan_barrier(board, (3, 3), set(), [((3, 5), 1.0)])
    common = {"barriers_left": 10, "steps_remaining": 10, "total_steps": 35,
              "board_size": 7, "reserve": 3, "threshold": 0.5}
    assert should_spend(plan=plan, expected_distance=6.0, **common) is True
    assert should_spend(plan=plan, expected_distance=1.0, **common) is False


# ------------------------------------------------------------------- brains


def test_the_thief_runs_toward_room_not_merely_away(board):
    """A cell two steps away with the board behind it beats a far cul-de-sac."""
    brain = OpenSpaceThief(rng=random.Random(1))
    ctx = context(Role.THIEF, (1, 1), barriers=[(0, 2), (1, 2), (2, 2)], threat=(3, 3))
    move_type, _direction, target, _why, _claims = brain._decide_move(ctx)
    assert move_type is MoveType.MOVE
    assert target is not None


def test_the_thief_refuses_to_stand_next_to_the_officer(board):
    brain = OpenSpaceThief(rng=random.Random(1))
    ctx = context(Role.THIEF, (3, 3), threat=(3, 5))
    _mt, _direction, target, _why, _claims = brain._decide_move(ctx)
    assert ctx.state.board.distance(target, (3, 5)) >= 2


def test_a_sealed_in_thief_concedes_rather_than_stalling(board):
    brain = OpenSpaceThief(rng=random.Random(1))
    ctx = context(Role.THIEF, (0, 0), barriers=[(0, 1), (1, 0)])
    move_type, direction, target, why, claims = brain._decide_move(ctx)
    assert move_type is MoveType.HOLD
    assert direction is None
    assert target == (0, 0)
    assert "sealed in" in why
    assert claims is False


def test_the_officer_claims_a_capture_when_confident(board):
    brain = ArchitectPolice(rng=random.Random(1))
    ctx = context(Role.POLICE, (3, 3), threat=(3, 4))
    move_type, _direction, target, _why, claims = brain._decide_move(ctx)
    assert move_type is MoveType.MOVE
    assert target == (3, 4)
    assert claims is True


def test_the_officer_stays_silent_when_it_is_only_guessing(board):
    """Claiming reveals our exact cell, so an uncertain officer says nothing."""
    brain = ArchitectPolice(rng=random.Random(1))
    ctx = context(Role.POLICE, (0, 0))  # uniform belief: no idea where they are
    _mt, _direction, _target, _why, claims = brain._decide_move(ctx)
    assert claims is False


def test_the_officer_extends_an_existing_wall_when_the_thief_is_far(board):
    """Anchored cells continue a fence; isolated ones are islands to walk around."""
    brain = ArchitectPolice(rng=random.Random(1), tuning={"wall_threshold": 1.0})
    ctx = context(Role.POLICE, (3, 3), barriers=[(2, 2), (2, 4)], threat=(6, 6),
                  steps_remaining=5)
    move_type, _direction, target, _why, _claims = brain._decide_move(ctx)
    assert move_type is MoveType.BARRIER
    assert target == (2, 3)   # the cell that closes the gap between the two walls


def test_a_boxed_in_officer_holds_instead_of_crashing(board):
    brain = ArchitectPolice(rng=random.Random(1))
    ctx = context(Role.POLICE, (0, 0), barriers=[(0, 1), (1, 0)])
    ctx.state.my_barriers = 14  # quota spent, nowhere to go
    move_type, direction, _target, _why, _claims = brain._decide_move(ctx)
    assert move_type is MoveType.HOLD
    assert direction is None


def test_brains_are_deterministic_given_the_same_state(board):
    first = ArchitectPolice(rng=random.Random(7))._decide_move(context(Role.POLICE, (2, 2), threat=(5, 5)))
    second = ArchitectPolice(rng=random.Random(7))._decide_move(context(Role.POLICE, (2, 2), threat=(5, 5)))
    assert first[:3] == second[:3]


# ------------------------------------------------------------------ factory


def test_the_factory_loads_a_dotted_selector():
    assert load_brain_cls("p2p_chase.strategy.thief_brain:OpenSpaceThief") is OpenSpaceThief


@pytest.mark.parametrize("selector,message", [
    ("no-colon-here", "Malformed strategy selector"),
    ("p2p_chase.nope:Thing", "Cannot import strategy module"),
    ("p2p_chase.strategy.thief_brain:Nope", "has no attribute"),
    ("p2p_chase.domain.board:Board", "not a BrainBase subclass"),
])
def test_a_bad_selector_is_reported_precisely(selector, message):
    with pytest.raises(ConfigError, match=message):
        load_brain_cls(selector)


def test_the_configured_brains_are_ours(config):
    assert resolve_brain_cls(config, Role.POLICE) is ArchitectPolice
    assert resolve_brain_cls(config, Role.THIEF) is OpenSpaceThief


def test_an_unset_selector_falls_back_to_the_shipped_brain(config):
    config.override("strategy.police_class", None)
    assert resolve_brain_cls(config, Role.POLICE) is ArchitectPolice


def test_resolve_brain_injects_the_tuning_block(config):
    brain = resolve_brain(config, Role.POLICE)
    assert isinstance(brain, ArchitectPolice)
    assert brain.tuning["wall_threshold"] == 3.0


def test_tuning_falls_back_when_a_value_is_unusable():
    brain = ArchitectPolice(tuning={"wall_threshold": "not-a-number"})
    assert brain._tune("wall_threshold", 3.0) == 3.0


def test_the_base_brain_demands_a_policy():
    class Bare(BrainBase):
        role = Role.THIEF

    with pytest.raises(NotImplementedError):
        Bare()._decide_move(context(Role.THIEF, (3, 3)))
