"""The sealed ``move`` field must stay inside the agreed move set.

An opponent replaying our revealed records against the signed
``move_set`` (N/S/E/W/STAY) has to be able to validate every move. An internal
action name such as ``BARRIER:E`` is outside that set, so a strict auditor
refuses to counter-sign the series — an honest game lost to a vocabulary
mismatch. Where a wall went belongs in ``barrier_placed``, never inside the
move field.
"""

import re

from p2p_chase.constants import Direction, MoveType, Role
from p2p_chase.domain.own_state import OwnGameState, wire_move

LEGAL = {"N", "S", "E", "W", "STAY"}


def test_a_move_seals_as_its_bare_direction() -> None:
    assert wire_move(MoveType.MOVE, Direction.E) == "E"
    assert wire_move(MoveType.MOVE, Direction.N) == "N"


def test_a_barrier_seals_as_stay_because_the_officer_forgoes_movement() -> None:
    assert wire_move(MoveType.BARRIER, Direction.E) == "STAY"


def test_holding_seals_as_stay() -> None:
    assert wire_move(MoveType.HOLD, None) == "STAY"


ORTHOGONAL = (Direction.N, Direction.S, Direction.E, Direction.W)


def test_every_action_on_the_standard_board_stays_inside_the_agreed_move_set() -> None:
    for move_type in MoveType:
        for direction in (*ORTHOGONAL, None):
            assert wire_move(move_type, direction) in LEGAL


def test_a_diagonal_passes_through_as_itself_for_a_negotiated_variant_board() -> None:
    """Diagonals are only reachable when both peers signed a move_set containing
    them, so echoing the direction is right — the signed set, not this function,
    decides what is legal."""
    assert wire_move(MoveType.MOVE, Direction.NE) == "NE"


def test_the_state_log_records_a_wire_legal_token_for_a_real_barrier() -> None:
    state = OwnGameState(Role.POLICE, (3, 3), 7)
    assert state.apply_move(MoveType.BARRIER, Direction.E, barriers_max=14)
    entry = state.log[-1]

    assert entry["wire_move"] == "STAY"
    assert entry["wire_move"] in LEGAL
    assert entry["barrier"] == [3, 4], "the wall's cell travels separately"
    assert entry["move"] == "BARRIER:E", "the richer internal name is kept, not published"


def test_the_state_log_records_a_wire_legal_token_for_a_real_move() -> None:
    state = OwnGameState(Role.THIEF, (3, 3), 7)
    assert state.apply_move(MoveType.MOVE, Direction.S)

    assert state.log[-1]["wire_move"] == "S"
    assert state.log[-1]["barrier"] is None


def test_no_sealed_token_ever_carries_a_colon() -> None:
    """The regression guard: `BARRIER:E` and `MOVE:E` must never reach the field."""
    state = OwnGameState(Role.POLICE, (3, 3), 7)
    state.apply_move(MoveType.MOVE, Direction.E)
    state.apply_move(MoveType.BARRIER, Direction.N, barriers_max=14)
    state.apply_move(MoveType.HOLD, None)

    for entry in state.log:
        assert not re.search(r":", entry["wire_move"])
        assert entry["wire_move"] in LEGAL
