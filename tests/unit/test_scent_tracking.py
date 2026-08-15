"""The scent field names the opponent's cell, and the filter must hear it.

Deposits merge by maximum and the field decays multiplicatively, so a received
grid peaks on the cell the opponent occupies now and trails its recent path behind
at ``peak * (1 - rho)^k``. Anything that fails to follow that peak is discarding
the only exact positional evidence the protocol provides.

The regression these tests exist for is not hypothetical: with the gentle
``1 + w*I`` weighting the filter converged on the *start* of the opponent's trail
and finished a live sub-game six cells adrift, thirty times more confident in a
cell abandoned ten moves earlier than in the one being stood on. Our thief walked
onto the officer's square believing it was six steps clear.
"""

import pytest

from p2p_chase.domain.belief import BeliefGrid
from p2p_chase.domain.board import Board
from p2p_chase.domain.smell import SmellField
from p2p_chase.strategy.decode import ScentTracker, decode_position, peak_cell

#: The officer's real path from the sub-game we lost, reconstructed from the log
#: the opponent published. It is a plain walk from (0,0) to the corner we died in.
LOSING_PATH = [
    (0, 1), (1, 1), (1, 2), (2, 2), (2, 3), (3, 3),
    (3, 4), (3, 5), (4, 5), (5, 5), (6, 5),
]


@pytest.fixture
def board() -> Board:
    return Board(7)


def _field() -> SmellField:
    return SmellField(board_size=7, grid_size=5, decay=0.10, min_center=0.5)


def _walk(path, board, *, start=(0, 0)):
    """Replay a path, yielding the grid each turn as the opponent would send it."""
    scent = _field()
    belief = BeliefGrid(board, smell_trust=4.0)
    belief.collapse_to(start)
    for cell in path:
        scent.deposit(cell, 0.9)
        scent.decay_all()
        yield cell, scent.snapshot(), belief


def test_the_field_peaks_on_the_cell_being_stood_on(board):
    for cell, grid, _belief in _walk(LOSING_PATH, board):
        assert peak_cell(grid, board) == cell


def test_the_filter_tracks_the_opponent_exactly_along_the_losing_path(board):
    errors = []
    for cell, grid, belief in _walk(LOSING_PATH, board):
        belief.predict(set(), stay_allowed=True)
        belief.observe_scent_peak(grid)
        best = belief.most_likely()
        errors.append(abs(best[0] - cell[0]) + abs(best[1] - cell[1]))
    assert errors == [0] * len(LOSING_PATH), f"belief drifted: {errors}"


def test_unscented_cells_are_penalised_not_merely_ignored(board):
    """The reservoir bug: weighting only the named cells leaves mass nowhere to lose."""
    belief = BeliefGrid(board, smell_trust=4.0)
    scent = _field()
    scent.deposit((6, 6), 0.9)
    grid = scent.snapshot()

    far = (0, 0)
    assert far not in {tuple(int(n) for n in k.split(",")) for k in grid}
    before = belief.probability(far)
    belief.observe_scent_peak(grid)
    assert belief.probability(far) < before


def test_an_empty_field_leaves_the_belief_untouched(board):
    belief = BeliefGrid(board, smell_trust=4.0)
    belief.collapse_to((2, 2))
    before = belief.as_matrix()
    belief.observe_scent_peak({})
    assert belief.as_matrix() == before


# ------------------------------------------------------------------- integrity


def test_a_peak_that_teleports_is_refused(board):
    decoded = decode_position({"6,6": 0.9}, board, set(), previous=(0, 0))
    assert decoded.trusted is False
    assert decoded.cell is None


def test_a_peak_inside_a_wall_is_refused(board):
    decoded = decode_position({"3,3": 0.9}, board, {(3, 3)}, previous=(3, 2))
    assert decoded.trusted is False


def test_a_first_peak_one_step_from_the_signed_start_is_accepted(board):
    """The opponent moves before it deposits, so the opening field is never on
    the start cell. Rejecting it here latched distrust before the first turn."""
    for opening in ((0, 0), (0, 1), (1, 0)):
        decoded = decode_position({f"{opening[0]},{opening[1]}": 0.9}, board, set(),
                                  None, expected_start=(0, 0))
        assert decoded.trusted is True, opening
        assert decoded.cell == opening


def test_a_first_peak_far_from_the_signed_start_is_refused(board):
    decoded = decode_position({"5,5": 0.9}, board, set(), None, expected_start=(0, 0))
    assert decoded.trusted is False


def test_a_step_onto_an_adjacent_cell_is_accepted(board):
    decoded = decode_position({"3,4": 0.9}, board, set(), previous=(3, 3))
    assert decoded.trusted is True
    assert decoded.cell == (3, 4)


def test_distrust_latches_for_the_rest_of_the_sub_game(board):
    """A field that has already contradicted geometry does not get a second chance."""
    tracker = ScentTracker(board, expected_start=(0, 0))
    assert tracker.update({"0,0": 0.9}, set()).trusted is True

    assert tracker.update({"6,6": 0.9}, set()).trusted is False
    # A perfectly plausible field afterwards must still be refused.
    assert tracker.update({"0,1": 0.9}, set()).trusted is False
    assert tracker.failure


def test_a_silent_opponent_is_not_treated_as_a_cheat(board):
    """No scent is uninformative, not evidence of forgery."""
    tracker = ScentTracker(board, expected_start=(0, 0))
    result = tracker.update({}, set())
    assert result.trusted is True
    assert result.cell is None


# --------------------------------------------------------------- wire shape


def test_the_audit_reveal_carries_exactly_three_keys():
    """The reference peer builds this with ``cls(**data)`` and raises on extras.

    An unknown key is not ignored there -- it kills the opponent's process at the
    audit, after a complete and otherwise valid match. This guard exists because
    a well-meant ``commit_scheme`` field, added to explain our hashing to a peer
    whose auditor disagreed with ours, did exactly that against the course
    reference. Anything we want to tell an opponent about our construction goes
    in the report or in writing, never on the wire.
    """
    from dataclasses import fields

    from p2p_chase.domain.protocol import AuditPayload

    assert {f.name for f in fields(AuditPayload)} == {"sender", "records", "result_claim"}


def test_a_strict_peer_can_rebuild_our_audit_reveal():
    """Simulates the reference's ``cls(**data)`` over what we actually send."""
    from p2p_chase.domain.protocol import AuditPayload

    sent = AuditPayload(sender="thief", records=[], result_claim="survival").to_dict()
    AuditPayload(**sent)  # must not raise
