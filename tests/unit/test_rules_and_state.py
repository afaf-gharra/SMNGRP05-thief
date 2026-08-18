"""Local truth, the barrier rule, and the three ways a run ends."""

import pytest

from p2p_chase.constants import Direction, MoveType, Role
from p2p_chase.domain.own_state import OwnGameState
from p2p_chase.domain.rules import GameRules

MOVES = ["N", "S", "E", "W", "STAY"]


def state(role=Role.THIEF, start=(3, 3)):
    own = OwnGameState(role, start, 7, MOVES)
    own.set_quota(14)
    return own


def test_a_legal_step_moves_and_is_logged():
    own = state()
    assert own.apply_move(MoveType.MOVE, Direction.N) is True
    assert own.position == (2, 3)
    assert own.step_number == 1
    assert own.log[-1]["move"] == "MOVE:N"


def test_an_illegal_step_changes_nothing():
    own = state(start=(0, 0))
    assert own.apply_move(MoveType.MOVE, Direction.N) is False
    assert own.position == (0, 0)
    assert own.step_number == 0


def test_visited_counts_unique_cells_only():
    own = state()
    own.apply_move(MoveType.MOVE, Direction.N)
    own.apply_move(MoveType.MOVE, Direction.S)
    assert own.unique_cells == 2


def test_holding_still_does_not_add_a_visit():
    own = state()
    own.apply_move(MoveType.HOLD, None)
    assert own.unique_cells == 1
    assert own.step_number == 1


def test_a_thief_cannot_place_barriers():
    assert state(Role.THIEF).apply_move(MoveType.BARRIER, Direction.N, 14) is False


def test_the_officer_seals_an_adjacent_cell():
    own = state(Role.POLICE, (3, 3))
    assert own.apply_move(MoveType.BARRIER, Direction.N, 14) is True
    assert (2, 3) in own.barriers
    assert own.my_barriers == 1
    assert own.last_barrier() == (2, 3)


def test_the_barrier_quota_is_enforced():
    own = state(Role.POLICE, (0, 0))
    assert own.apply_move(MoveType.BARRIER, Direction.S, 1) is True
    assert own.apply_move(MoveType.BARRIER, Direction.E, 1) is False
    assert own.my_barriers == 1


def test_a_sealed_cell_cannot_be_sealed_twice():
    own = state(Role.POLICE, (3, 3))
    own.apply_move(MoveType.BARRIER, Direction.N, 14)
    own.note_barrier((3, 4))
    assert own.apply_move(MoveType.BARRIER, Direction.E, 14) is False


def test_barriers_block_the_officer_too():
    own = state(Role.POLICE, (3, 3))
    own.apply_move(MoveType.BARRIER, Direction.N, 14)
    assert own.apply_move(MoveType.MOVE, Direction.N) is False


def test_last_barrier_is_none_after_an_ordinary_move():
    own = state(Role.POLICE, (3, 3))
    own.apply_move(MoveType.MOVE, Direction.N)
    assert own.last_barrier() is None


def test_immobilised_only_when_every_exit_is_sealed():
    own = state(Role.THIEF, (0, 0))
    assert own.is_immobilised() is False
    own.note_barrier((0, 1))
    own.note_barrier((1, 0))
    assert own.is_immobilised() is True


# --------------------------------------------------------------------- rules


def test_survival_is_claimed_at_the_threshold():
    rules = GameRules(survival_threshold=5)
    own = state(Role.THIEF)
    for _ in range(4):
        own.apply_move(MoveType.HOLD, None)
    assert rules.thief_result(own) is None
    own.apply_move(MoveType.HOLD, None)
    assert rules.thief_result(own) == "survival"


def test_the_officer_never_claims_survival():
    assert GameRules(1).thief_result(state(Role.POLICE)) is None


def test_a_capture_claim_is_answered_honestly():
    own = state(Role.THIEF, (2, 4))
    assert GameRules.is_captured(own, (2, 4)) is True
    assert GameRules.is_captured(own, (2, 5)) is False


def test_a_thief_with_no_legal_move_is_captured():
    """Mandatory rule 47: enclosure is a capture even though nobody touched it."""
    own = state(Role.THIEF, (0, 0))
    own.note_barrier((0, 1))
    own.note_barrier((1, 0))
    assert GameRules.is_sealed_in(own) is True
    assert GameRules(35).evaluate_self(own) == "capture"


def test_enclosure_only_applies_to_the_thief():
    own = state(Role.POLICE, (0, 0))
    own.note_barrier((0, 1))
    own.note_barrier((1, 0))
    assert GameRules.is_sealed_in(own) is False


def test_out_of_moves_tracks_the_agreed_ceiling():
    rules = GameRules(survival_threshold=35, max_moves=3)
    own = state(Role.THIEF)
    for _ in range(3):
        own.apply_move(MoveType.HOLD, None)
    assert rules.out_of_moves(own) is True


@pytest.mark.parametrize(
    "move_set,allowed",
    [(["N", "S", "E", "W", "STAY"], True), (["N", "S", "E", "W"], False)],
)
def test_standing_still_obeys_the_negotiated_move_set(move_set, allowed):
    own = OwnGameState(Role.THIEF, (3, 3), 7, move_set)
    assert own.apply_move(MoveType.HOLD, None) is allowed


def test_a_barrier_on_the_thiefs_own_cell_is_a_capture(config):
    """Rule 46, self-checked rather than waiting to be told.

    We used to detect a seal only through the officer's capture claim, so an
    opponent who sealed us and said nothing left us playing on to step 35 and
    filing a survival. Two honest teams then file contradictory reports, which
    rule 35 scores as nobody winning.
    """
    from p2p_chase.constants import Role
    from p2p_chase.domain.own_state import OwnGameState
    from p2p_chase.domain.rules import GameRules

    state = OwnGameState(Role.THIEF, (3, 3), 7, ["N", "S", "E", "W", "STAY"])
    rules = GameRules(35)
    assert rules.is_sealed_in(state) is False

    state.note_barrier((3, 3))          # the officer walls the cell we stand on
    assert rules.is_sealed_in(state) is True


def test_a_thief_with_no_step_is_captured_even_though_stay_is_legal(config):
    """Rule 47: STAY is in the move set and does not rescue a sealed thief."""
    from p2p_chase.constants import Role
    from p2p_chase.domain.own_state import OwnGameState
    from p2p_chase.domain.rules import GameRules

    state = OwnGameState(Role.THIEF, (0, 0), 7, ["N", "S", "E", "W", "STAY"])
    assert state.can_stay is True
    for wall in ((0, 1), (1, 0)):
        state.note_barrier(wall)

    assert GameRules(35).is_sealed_in(state) is True
