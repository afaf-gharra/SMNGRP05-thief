"""The two brains and the selector that loads them."""

import random

import pytest

from p2p_chase.constants import MoveType, Role
from p2p_chase.domain.belief import BeliefGrid
from p2p_chase.domain.own_state import OwnGameState
from p2p_chase.domain.trust import TrustEstimator
from p2p_chase.exceptions import ConfigError
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


def test_the_officer_seals_the_thief_rather_than_stepping_onto_it(board):
    """A seal cannot be answered; a step can.

    Stepping onto the thief's square is a claim it gets to move away from on its
    own turn. Sealing that square ends the sub-game immediately under rule 46,
    and the thief has already spent its move. Both cost us the turn, so when we
    are certain enough to claim at all we should always take the seal.
    """
    brain = ArchitectPolice(rng=random.Random(1))
    ctx = context(Role.POLICE, (3, 3), threat=(3, 4))
    move_type, _direction, target, _why, claims = brain._decide_move(ctx)
    assert move_type is MoveType.BARRIER
    assert target == (3, 4)
    assert claims is True


def test_the_officer_steps_onto_the_thief_when_its_barriers_are_spent(board):
    """With no wall left the claim is still worth making, just the weaker way."""
    brain = ArchitectPolice(rng=random.Random(1))
    ctx = context(Role.POLICE, (3, 3), threat=(3, 4))
    ctx.state.my_barriers = 14
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


def test_the_officer_closes_the_gap_between_two_walls_in_front_of_the_thief(board):
    """Anchored cells continue a fence; isolated ones are islands to walk around.

    The thief sits beyond the gap, so sealing it is worth a turn. Previously this
    case was written with the thief in the far corner, which asserted the very
    behaviour that lost us three sub-games.
    """
    brain = ArchitectPolice(rng=random.Random(1), tuning={"wall_threshold": 1.0})
    ctx = context(Role.POLICE, (3, 3), barriers=[(2, 2), (2, 4)], threat=(1, 3),
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
