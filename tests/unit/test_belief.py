"""The Bayesian filter: prediction, evidence, testimony and certainty."""

import pytest

from p2p_chase.domain.belief import BeliefGrid


@pytest.fixture
def belief(board):
    return BeliefGrid(board, smell_trust=4.0)


def total(grid: BeliefGrid) -> float:
    return sum(sum(row) for row in grid.as_matrix())


def test_starts_uniform_and_normalised(belief, board):
    assert total(belief) == pytest.approx(1.0)
    assert belief.probability((0, 0)) == pytest.approx(1 / board.cells)


def test_scent_concentrates_the_belief(belief):
    belief.observe_smell({"5,5": 0.9})
    assert belief.most_likely() == (5, 5)
    assert total(belief) == pytest.approx(1.0)


def test_prediction_spreads_mass_but_conserves_it(belief):
    belief.observe_smell({"3,3": 0.9})
    peak_before = belief.probability((3, 3))
    belief.predict()
    assert belief.probability((3, 3)) < peak_before
    assert total(belief) == pytest.approx(1.0)


def test_prediction_does_not_leak_through_barriers(belief):
    """A wall the officer paid for must actually constrain the filter.

    Start from certainty that the opponent is south of a full-width wall, then
    let the motion model run. A naive 3x3 smear would seep mass northwards; a
    model that walks the real graph cannot.
    """
    wall = {(3, col) for col in range(7)}
    belief.exclude_all([(row, col) for row in range(4) for col in range(7)])
    for _ in range(8):
        belief.predict(wall)
    northern_mass = sum(sum(row) for row in belief.as_matrix()[:4])
    assert northern_mass == pytest.approx(0.0, abs=1e-9)
    assert sum(sum(row) for row in belief.as_matrix()[4:]) == pytest.approx(1.0)


def test_exclude_rules_a_cell_out(belief):
    belief.observe_smell({"2,2": 0.9})
    belief.exclude((2, 2))
    assert belief.probability((2, 2)) == 0.0
    assert total(belief) == pytest.approx(1.0)


def test_excluding_everything_falls_back_to_ignorance(belief, board):
    belief.exclude_all([(r, c) for r in range(7) for c in range(7)])
    assert belief.probability((0, 0)) == pytest.approx(1 / board.cells)


def test_a_trusted_hint_lifts_the_named_region(belief):
    region = {(0, c) for c in range(7)}
    before = belief.probability((0, 3))
    belief.observe_region(region, trust=0.9)
    assert belief.probability((0, 3)) > before


def test_a_hint_from_a_known_liar_is_inverted(belief):
    """Below trust 0.5 the claim should push mass *away* from the named region."""
    region = {(0, c) for c in range(7)}
    before = belief.probability((0, 3))
    belief.observe_region(region, trust=0.1)
    assert belief.probability((0, 3)) < before


def test_an_uninformative_talker_moves_nothing(belief):
    before = belief.as_matrix()
    belief.observe_region({(0, 0)}, trust=0.5)
    assert belief.as_matrix() == before


def test_collapse_records_a_sighting_without_becoming_absolute(belief):
    belief.collapse_to((6, 6))
    assert belief.most_likely() == (6, 6)
    assert belief.probability((6, 6)) > 0.9
    assert belief.probability((0, 0)) > 0.0     # recoverable, not a point mass


def test_collapse_ignores_an_off_board_cell(belief):
    belief.collapse_to((99, 99))
    assert total(belief) == pytest.approx(1.0)


def test_top_cells_are_ordered_hottest_first(belief):
    belief.observe_smell({"1,1": 0.9, "2,2": 0.4})
    cells = belief.top_cells(3)
    assert cells[0][0] == (1, 1)
    assert cells[0][1] >= cells[1][1] >= cells[2][1]


def test_mass_within_a_radius_covers_the_neighbourhood(belief):
    belief.observe_smell({"3,3": 0.9})
    assert belief.mass_within((3, 3), 1) > belief.mass_within((0, 0), 1)


def test_probability_outside_the_board_is_zero(belief):
    assert belief.probability((9, 9)) == 0.0
