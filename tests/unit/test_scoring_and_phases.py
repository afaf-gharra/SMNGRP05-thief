"""The points table, the tie rule, and the turn state machine."""

import pytest

from p2p_chase.domain import scoring
from p2p_chase.domain.phases import GamePhaseMachine, Phase
from p2p_chase.exceptions import PhaseError

TABLE = scoring.DEFAULT_SCORING
ROLES = {"team-a": "police", "team-b": "thief"}


def test_capture_pays_the_officer_most_but_still_pays_the_thief():
    assert scoring.score_subgame("capture", ROLES, TABLE) == {"team-a": 20, "team-b": 5}


def test_survival_pays_the_thief_most_but_still_pays_the_officer():
    assert scoring.score_subgame("survival", ROLES, TABLE) == {"team-a": 5, "team-b": 10}


@pytest.mark.parametrize("result", ["timeout", "tamper_forfeit", "stopped"])
def test_a_technical_loss_zeroes_both_sides(result):
    assert scoring.score_subgame(result, ROLES, TABLE) == {"team-a": 0, "team-b": 0}


def test_scoring_falls_back_to_the_book_defaults_if_a_table_is_missing():
    assert scoring.score_subgame("capture", ROLES, {})["team-a"] == 20


def test_aggregate_sums_and_names_a_winner():
    outcome = scoring.aggregate([{"a": 20, "b": 5}, {"a": 5, "b": 10}], tie_score=2)
    assert outcome["total_score"] == {"a": 25, "b": 15}
    assert outcome["winner_group"] == "a"
    assert outcome["series_tie"] is False
    assert outcome["sub_games_won"] == {"a": 1, "b": 1}


def test_a_level_series_credits_both_sides_the_tie_score():
    outcome = scoring.aggregate([{"a": 20, "b": 5}, {"a": 5, "b": 20}], tie_score=2)
    assert outcome["series_tie"] is True
    assert outcome["winner_group"] is None
    assert outcome["total_score"] == {"a": 27, "b": 27}


def test_a_drawn_sub_game_counts_as_a_tie_not_a_win():
    outcome = scoring.aggregate([{"a": 0, "b": 0}], tie_score=2)
    assert outcome["ties"] == 1
    assert outcome["sub_games_won"] == {"a": 0, "b": 0}


# ------------------------------------------------------------- phase machine


def test_the_happy_path_cycles_back_to_waiting():
    machine = GamePhaseMachine()
    for phase in (
        Phase.COMPUTING_MOVE, Phase.COMMITTING, Phase.AWAITING_REVEAL,
        Phase.VERIFYING, Phase.WAITING_FOR_OPPONENT,
    ):
        machine.to(phase)
    assert machine.state is Phase.WAITING_FOR_OPPONENT
    assert machine.finished is False


def test_an_illegal_transition_raises_immediately():
    with pytest.raises(PhaseError, match="Illegal phase transition"):
        GamePhaseMachine().to(Phase.VERIFYING)


def test_the_error_names_the_legal_targets():
    with pytest.raises(PhaseError, match="COMPUTING_MOVE"):
        GamePhaseMachine().to(Phase.GAME_OVER)


def test_a_game_ending_on_our_own_move_goes_straight_to_audit():
    machine = GamePhaseMachine()
    machine.to(Phase.COMPUTING_MOVE)
    machine.to(Phase.COMMITTING)
    machine.to(Phase.AUDITING)
    machine.to(Phase.GAME_OVER)
    assert machine.finished is True


def test_failure_is_reachable_from_any_live_phase():
    machine = GamePhaseMachine()
    machine.to(Phase.COMPUTING_MOVE)
    machine.fail("opponent vanished")
    assert machine.state is Phase.TECHNICAL_LOSS
    assert machine.reason == "opponent vanished"
    assert machine.finished is True


def test_failing_a_finished_machine_is_a_no_op():
    machine = GamePhaseMachine()
    machine.fail("first")
    assert machine.fail("second") is Phase.TECHNICAL_LOSS


def test_terminal_states_have_no_exits():
    machine = GamePhaseMachine()
    machine.fail()
    with pytest.raises(PhaseError):
        machine.to(Phase.COMPUTING_MOVE)


def test_can_reports_without_raising():
    machine = GamePhaseMachine()
    assert machine.can(Phase.COMPUTING_MOVE) is True
    assert machine.can(Phase.VERIFYING) is False


def test_the_trail_records_the_route_taken():
    machine = GamePhaseMachine()
    machine.to(Phase.COMPUTING_MOVE)
    machine.to(Phase.COMMITTING)
    assert machine.path() == ["WAITING_FOR_OPPONENT", "COMPUTING_MOVE", "COMMITTING"]
