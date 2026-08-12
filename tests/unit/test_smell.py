"""The pheromone model: emission shape, the book's decay law, and the wire format."""

import pytest

from p2p_chase.domain.smell import (
    GAUSSIAN,
    LINEAR,
    MULTIPLICATIVE,
    SmellField,
    parse_cell,
)


def field(**kwargs):
    defaults = {"board_size": 7, "grid_size": 5, "decay": 0.10, "min_center": 0.5}
    return SmellField(**{**defaults, **kwargs})


def test_emission_peaks_at_the_agent_and_falls_away():
    window = field().emission((3, 3), 0.9)
    assert window[(3, 3)] == 0.9
    assert window[(3, 4)] < window[(3, 3)]
    assert window[(1, 1)] < window[(3, 4)]


def test_gaussian_falloff_reproduces_the_book_figure():
    """Appendix figure 4: centre 0.90, then 0.62, 0.42, 0.20, 0.14, 0.04."""
    window = field(falloff=GAUSSIAN).emission((3, 3), 0.9)
    assert window[(3, 3)] == 0.9
    assert window[(3, 4)] == pytest.approx(0.62, abs=0.01)
    assert window[(2, 2)] == pytest.approx(0.42, abs=0.01)
    assert window[(3, 5)] == pytest.approx(0.20, abs=0.01)
    assert window[(2, 1)] == pytest.approx(0.14, abs=0.01)
    assert window[(1, 1)] == pytest.approx(0.04, abs=0.01)


def test_linear_falloff_matches_the_reference_scale():
    window = field(falloff=LINEAR).emission((3, 3), 0.9)
    assert window[(3, 4)] == pytest.approx(0.6, abs=0.001)
    assert window[(3, 5)] == pytest.approx(0.3, abs=0.001)


def test_emission_is_clipped_at_the_board_edge():
    window = field().emission((0, 0), 0.9)
    assert all(r >= 0 and c >= 0 for r, c in window)


def test_decay_subtracts_by_default_because_that_is_what_the_league_plays():
    """tau(t+1) = tau(t) - rho, the reference's `subtractive_chebyshev_v1`."""
    smell = field()
    smell.deposit((3, 3), 0.9)
    smell.decay_all()
    assert smell.intensity_at((3, 3)) == pytest.approx(0.80, abs=1e-4)
    smell.decay_all()
    assert smell.intensity_at((3, 3)) == pytest.approx(0.70, abs=1e-4)


def test_the_books_multiplicative_law_is_still_available():
    """tau(t+1) = (1 - rho) * tau(t): kept, because the book writes it this way.

    The two forms differ by one hundredth after a single turn, which is exactly
    the kind of gap that plays a clean match and then fails an audit. Neither is
    wrong; the mode simply has to be agreed and declared, so both live here.
    """
    smell = field(decay_mode=MULTIPLICATIVE)
    smell.deposit((3, 3), 0.9)
    smell.decay_all()
    assert smell.intensity_at((3, 3)) == pytest.approx(0.81, abs=1e-4)
    smell.decay_all()
    assert smell.intensity_at((3, 3)) == pytest.approx(0.729, abs=1e-4)


def test_a_subtractive_trail_reaches_zero_in_a_fixed_number_of_turns():
    """Unlike the multiplicative law it terminates, so dead scent cannot linger."""
    smell = field()
    smell.deposit((3, 3), 0.9)
    for _ in range(9):
        smell.decay_all()
    assert smell.intensity_at((3, 3)) == 0.0


def test_a_single_deposit_stays_readable_for_about_seven_turns():
    smell = field(decay_mode=MULTIPLICATIVE)
    smell.deposit((3, 3), 0.9)
    for _ in range(7):
        smell.decay_all()
    assert smell.intensity_at((3, 3)) < 0.45      # below half peak
    assert smell.intensity_at((3, 3)) > 0.40      # but still clearly present


def test_deposit_below_the_agreed_minimum_is_refused():
    with pytest.raises(ValueError, match="below the agreed minimum"):
        field().deposit((3, 3), 0.1)


def test_deposits_merge_by_maximum():
    smell = field()
    smell.deposit((3, 3), 0.9)
    smell.decay_all()
    smell.deposit((3, 4), 0.9)
    assert smell.intensity_at((3, 4)) == 0.9


def test_absorb_round_trips_a_snapshot():
    source, sink = field(), field()
    source.deposit((2, 2), 0.9)
    sink.absorb(source.snapshot())
    assert sink.intensity_at((2, 2)) == 0.9


def test_absorb_ignores_junk_and_off_board_cells():
    smell = field()
    smell.absorb({"not-a-cell": 0.9, "99,99": 0.9, "1,1": 0.4})
    assert smell.snapshot() == {"1,1": 0.4}


def test_strongest_cell_is_the_freshest_deposit():
    smell = field()
    smell.deposit((0, 0), 0.9)
    smell.decay_all()
    smell.deposit((5, 5), 0.9)
    assert smell.strongest_cell() == (5, 5)


def test_strongest_cell_is_none_on_an_empty_field():
    assert field().strongest_cell() is None


def test_dead_cells_are_dropped_from_the_snapshot():
    smell = field()
    smell.deposit((3, 3), 0.9)
    for _ in range(200):
        smell.decay_all()
    assert smell.snapshot() == {}


@pytest.mark.parametrize("key,expected", [("1,2", (1, 2)), (" 3 , 4 ", (3, 4)), ("x", None)])
def test_parse_cell(key, expected):
    assert parse_cell(key) == expected
