"""We must never tell an opponent where we actually are.

In the series we lost, eleven of twelve hints in one sub-game were truthful and
named our real sector — "Every alley around southeast knows me better than you
do", sent from (6,5). The planner had decided that truth was cheap because the
opponent could smell us anyway. Against an opponent that reads the scent it was
merely useless; against one that does not, it was the whole game handed over.
"""

import random
import re

import pytest

from p2p_chase.constants import Intent, Role
from p2p_chase.domain.board import Board
from p2p_chase.strategy.talk import landmarks as geo
from p2p_chase.strategy.talk.bluff import BluffPlanner


@pytest.fixture
def board() -> Board:
    return Board(7)


def _words(sentence: str) -> set[str]:
    """Whole words only — the gazetteer holds short names like "un" that would
    otherwise match inside ordinary words such as "found"."""
    return set(re.findall(r"[a-z']+", sentence.lower()))


def _planner(board, lie_rate=0.45, seed=1) -> BluffPlanner:
    planner = BluffPlanner(board, TrustEstimatorFactory(board), lie_rate=lie_rate,
                           rng=random.Random(seed))
    return planner


def TrustEstimatorFactory(board):  # noqa: N802 - reads as a constructor at call sites
    from p2p_chase.domain.trust import TrustEstimator

    return TrustEstimator(board_cells=board.cells)


def test_our_true_sector_is_never_named(board):
    """Across many turns and urgencies, the honest sector must never be spoken."""
    planner = _planner(board)
    for step in range(200):
        choice = planner.choose("south-east", "north-west", urgency=step / 200, step=step)
        assert choice.sector != "south-east", f"leaked our sector on step {step}"


def test_a_spatial_claim_is_always_a_decoy(board):
    planner = _planner(board)
    spatial = [
        planner.choose("south-east", "north-west", urgency=0.9, step=step)
        for step in range(200)
    ]
    named = [choice for choice in spatial if choice.sector]
    assert named, "the planner should still be willing to mislead"
    assert all(choice.sector == "north-west" for choice in named)
    assert all(choice.intent == Intent.LIE.value for choice in named)


def test_saying_nothing_is_recorded_as_honest(board):
    """An empty claim is not a lie, and the sealed intent flag must say so."""
    planner = _planner(board, lie_rate=0.0)
    choice = planner.choose("south-east", "north-west", urgency=0.0, step=1)
    assert choice.sector == ""
    assert choice.intent == Intent.TRUTH.value


def test_an_empty_sector_produces_a_sentence_with_no_place_in_it(board):
    """The composed hint must not accidentally name somewhere."""
    from p2p_chase.strategy.talk.templates import TemplateTalker

    talker = TemplateTalker(board, "New York", max_words=15, rng=random.Random(3))
    places = {
        word.lower()
        for words in talker._gazetteer.values()
        for word in words
    }
    for _ in range(50):
        assert not places & _words(talker.vague())


def test_no_frame_denies_the_sector_it_is_handed(board):
    """A negating frame inverts the claim and can label a falsehood as truth."""
    from p2p_chase.strategy.talk.templates import _POLICE_FRAMES, _THIEF_FRAMES

    for frame in (*_THIEF_FRAMES, *_POLICE_FRAMES):
        lowered = frame.lower()
        assert " not " not in lowered
        assert "never" not in lowered
        assert "nowhere left" in lowered or "nowhere" not in lowered


def test_the_thief_speaks_without_naming_itself(board):
    """End to end: a thief hint must not contain the sector the thief is in."""
    from p2p_chase.strategy.talk.templates import TemplateTalker

    talker = TemplateTalker(board, "New York", max_words=15, rng=random.Random(11))
    true_sector = geo.cell_sector(board, (6, 5))
    own_words = {w.lower() for w in (talker._gazetteer.get(true_sector) or [])}
    leaked = 0
    for step in range(60):
        choice = talker.planner.choose(true_sector, geo.opposite(true_sector), 0.5, step)
        leaked += bool(own_words & _words(talker._compose(Role.THIEF, choice)))
    assert leaked == 0
