"""The lie detector: reading a hint, and learning who lies."""

import pytest

from p2p_chase.domain.hint_parser import parse_hint, tokenize
from p2p_chase.domain.trust import TrustEstimator
from p2p_chase.strategy.talk import landmarks as geo


@pytest.fixture
def landmarks(board):
    return geo.landmark_index(board, "New York")


def test_tokenize_lowercases_and_drops_punctuation():
    assert tokenize("Heading North, fast!") == ["heading", "north", "fast"]


def test_an_empty_hint_claims_nothing(board):
    assert not parse_hint("", board)
    assert not parse_hint("   ", board)


def test_a_hint_with_no_spatial_content_claims_nothing(board):
    assert not parse_hint("you will never take me alive", board)


def test_a_bearing_claims_the_matching_half(board):
    claim = parse_hint("slipping north through the alleys", board)
    assert claim
    assert (0, 3) in claim.cells
    assert (6, 3) not in claim.cells


def test_centre_and_edge_claim_different_shapes(board):
    centre = parse_hint("holed up midtown", board)
    edge = parse_hint("hugging the outskirts", board)
    assert (3, 3) in centre.cells
    assert (3, 3) not in edge.cells
    assert (0, 0) in edge.cells


def test_a_landmark_pins_a_region(board, landmarks):
    claim = parse_hint("ducking past brooklyn", board, landmarks)
    assert claim
    assert claim.cells


def test_negation_is_detected(board):
    assert parse_hint("nowhere near the north side", board).negated is True


# ---------------------------------------------------------------- estimator


def test_the_prior_is_agnostic():
    assert TrustEstimator().trust == pytest.approx(0.5)


def test_trust_rises_when_words_match_the_trail(board):
    trust = TrustEstimator()
    claim = parse_hint("moving north", board)
    scent = {(0, 3): 0.9, (1, 3): 0.6}
    for step in range(6):
        trust.score(step, claim, scent)
    assert trust.trust > 0.75


def test_trust_collapses_when_the_trail_contradicts_the_words(board):
    """The book's worked example: they say north, the scent says south-east."""
    trust = TrustEstimator()
    claim = parse_hint("moving north", board)
    scent = {(6, 6): 0.81, (5, 6): 0.63, (6, 5): 0.63}
    for step in range(6):
        trust.score(step, claim, scent)
    assert trust.trust < 0.25
    assert trust.estimated_lie_rate > 0.75


def test_trust_is_clamped_so_nobody_becomes_a_certainty(board):
    trust = TrustEstimator(floor=0.05, ceiling=0.95)
    claim = parse_hint("moving north", board)
    for step in range(200):
        trust.score(step, claim, {(0, 3): 0.9})
    assert trust.trust <= 0.95


def test_an_unfalsifiable_hint_carries_no_weight(board):
    trust = TrustEstimator()
    verdict = trust.score(1, parse_hint("catch me if you can", board), {(0, 0): 0.9})
    assert verdict.weight == 0.0
    assert trust.trust == pytest.approx(0.5)
    assert trust.hints_scored == 0


def test_a_hint_with_no_scent_evidence_carries_no_weight(board):
    trust = TrustEstimator()
    verdict = trust.score(1, parse_hint("moving north", board), {})
    assert verdict.weight == 0.0
    assert trust.trust == pytest.approx(0.5)


def test_a_vague_claim_covering_the_board_is_discounted(board):
    """Claiming half the board and being 'right' proves very little."""
    specific, vague = TrustEstimator(), TrustEstimator()
    scent = {(0, 3): 0.9}
    specific.score(1, parse_hint("midtown", board), scent)
    vague.score(1, parse_hint("north", board), scent)
    assert vague.history[0].weight <= specific.history[0].weight


def test_the_summary_reports_the_profile(board):
    trust = TrustEstimator()
    trust.score(1, parse_hint("moving north", board), {(0, 3): 0.9})
    summary = trust.summary()
    assert set(summary) == {
        "trust", "estimated_lie_rate", "hints_seen", "hints_scored", "alpha", "beta"
    }
    assert summary["hints_seen"] == 1
