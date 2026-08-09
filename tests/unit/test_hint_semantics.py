"""A hint about where someone *went* is not a hint about where they *are*.

The opponent that beat us reported headings — "I moved east", "I moved south" —
and we read each one as a claim to be standing in that third of the board. Their
officer opened in the north-west, stepped to (0,1), truthfully said "I moved
east", and our belief slid to the far side. Every honest report they made pushed
us further wrong, all match.
"""

import pytest

from p2p_chase.domain.board import Board
from p2p_chase.domain.hint_parser import parse_hint
from p2p_chase.strategy.talk import landmarks as geo


@pytest.fixture
def board() -> Board:
    return Board(7)


@pytest.fixture
def places(board) -> dict:
    return geo.landmark_index(board, "New York")


@pytest.mark.parametrize(
    "hint",
    [
        "I moved east.",
        "I moved south.",
        "I moved north.",
        "I moved west.",
        "heading north",
        "going west now",
        "stepped east",
    ],
)
def test_a_heading_claims_nothing_about_position(hint, board):
    claim = parse_hint(hint, board, {})
    assert claim.informative is False
    assert claim.cells == set()


@pytest.mark.parametrize(
    "hint",
    [
        "Every alley around east knows me better than you do.",
        "I am in the centre.",
        "cornered again",
        "out by the perimeter",
    ],
)
def test_a_location_claim_still_narrows_the_board(hint, board):
    assert parse_hint(hint, board, {}).informative is True


def test_a_landmark_after_a_travel_verb_is_still_a_place(board, places):
    """Only a bare bearing is a heading; "slipping past harlem" says where."""
    claim = parse_hint("Slipping past harlem while you waste time.", board, places)
    assert claim.informative is True
    assert claim.cells


def test_a_bearing_behind_a_preposition_is_still_a_place(board):
    """The preposition is what separates "moved east" from "around east"."""
    assert parse_hint("moved east", board, {}).informative is False
    assert parse_hint("lurking around east", board, {}).informative is True


def test_denials_are_detected(board):
    assert parse_hint("You will not find me near the centre.", board, {}).negated is True
    assert parse_hint("I am in the centre.", board, {}).negated is False


def test_a_credible_denial_drains_the_named_region(board):
    """The bug this guards: a denial used to *fill* the region it ruled out."""
    from p2p_chase.domain.belief import BeliefGrid

    named = parse_hint("I am in the centre.", board, {}).cells
    assert named

    trusted = BeliefGrid(board)
    trusted.observe_region(named, 0.9)          # a credible assertion
    denied = BeliefGrid(board)
    denied.observe_region(named, 1.0 - 0.9)     # the same claim, negated

    cell = next(iter(named))
    assert trusted.probability(cell) > denied.probability(cell)
