"""Turn a free-form natural-language hint into a spatial claim.

The protocol forbids exchanging coordinates (mandatory rule 27): agents may only
speak in ordinary language. That does not make the words meaningless — a hint
like *"slipping north past the park"* still narrows the board, and the point of
the game is that it might be a lie.

This module does the honest half of the work: it maps text onto a *set of cells*
the speaker is implicitly claiming to be in. Deciding whether to believe that
claim is :mod:`p2p_chase.domain.trust`'s job.

Parsing is intentionally keyword-based rather than model-based. It must be
deterministic — both peers replay these decisions during the audit — and it must
never stall a turn waiting on a network call.
"""

import re
from dataclasses import dataclass, field

from p2p_chase.constants import Cell
from p2p_chase.domain.board import Board

#: Words that name a compass bearing. Row grows downward, so "north" is low row.
_BEARINGS: dict[str, tuple[int, int]] = {
    "north": (-1, 0), "northern": (-1, 0), "up": (-1, 0), "uptown": (-1, 0),
    "top": (-1, 0), "above": (-1, 0),
    "south": (1, 0), "southern": (1, 0), "down": (1, 0), "downtown": (1, 0),
    "bottom": (1, 0), "below": (1, 0),
    "east": (0, 1), "eastern": (0, 1), "right": (0, 1), "eastside": (0, 1),
    "west": (0, -1), "western": (0, -1), "left": (0, -1), "westside": (0, -1),
}

_CENTRE_WORDS = frozenset(
    {"centre", "center", "middle", "midtown", "heart", "core", "central"}
)
_EDGE_WORDS = frozenset({"edge", "border", "outskirts", "perimeter", "rim", "wall"})
_CORNER_WORDS = frozenset({"corner", "cornered", "angle"})
_NEGATIONS = frozenset({"not", "never", "no", "nowhere", "far", "away", "opposite"})

#: Verbs of travel. A bearing *immediately* after one of these names a direction
#: of travel, not a part of the board, and the two mean entirely different things.
#:
#: An opponent whose hints read "I moved east" was telling us which way it had
#: stepped. We read every one as "I am somewhere in the eastern third", so an
#: officer starting in the north-west corner and stepping to (0,1) had us
#: shifting belief to the far side of the board — on its own honest report, every
#: turn, for a whole match.
#:
#: The preposition is what separates the two senses. "Moved east" is a heading;
#: "slipping past east" or "every alley around east" places the speaker somewhere.
#: So only a bare bearing directly following the verb is discarded, which leaves
#: ordinary location talk — including our own frames — parsed as before.
_TRAVEL_VERBS = frozenset(
    {
        "moved", "moving", "move", "went", "going", "go", "heading", "headed",
        "walked", "walking", "ran", "running", "stepped", "stepping", "turned",
        "turning", "slipping", "slipped", "cutting", "cut", "drove", "driving",
        "came", "coming", "left", "leaving", "travelled", "traveled",
    }
)

_WORD = re.compile(r"[a-z]+")


@dataclass
class SpatialClaim:
    """What a hint asserts about the speaker's whereabouts."""

    cells: set[Cell] = field(default_factory=set)
    bearings: list[tuple[int, int]] = field(default_factory=list)
    negated: bool = False
    informative: bool = False

    def __bool__(self) -> bool:
        return self.informative and bool(self.cells)


def tokenize(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


def parse_hint(text: str, board: Board, landmarks: dict[str, Cell] | None = None) -> SpatialClaim:
    """Extract the region a hint points at.

    Three signals are combined, in order of how specific they are: a named
    landmark from the agreed map area pins a cell directly; ``centre``/``edge``/
    ``corner`` name a shape; a compass bearing names a half-board. A hint that
    matches nothing is simply uninformative, which is a perfectly normal outcome
    and must not be mistaken for a lie.
    """
    words = tokenize(text)
    if not words:
        return SpatialClaim()
    claim = SpatialClaim(negated=any(word in _NEGATIONS for word in words))
    previous = ""

    for word in words:
        heading = previous in _TRAVEL_VERBS
        previous = word
        if landmarks and word in landmarks:
            claim.cells |= _disc(board, landmarks[word], radius=1)
            claim.informative = True
        if word in _CENTRE_WORDS:
            claim.cells |= _centre(board)
            claim.informative = True
        elif word in _CORNER_WORDS:
            claim.cells |= _corners(board)
            claim.informative = True
        elif word in _EDGE_WORDS:
            claim.cells |= _edge(board)
            claim.informative = True
        elif word in _BEARINGS and not heading:
            claim.bearings.append(_BEARINGS[word])

    for bearing in claim.bearings:
        claim.cells |= _half(board, bearing)
        claim.informative = True
    return claim


def _disc(board: Board, centre: Cell, radius: int) -> set[Cell]:
    return {
        (r, c)
        for r in range(board.size)
        for c in range(board.size)
        if board.distance((r, c), centre) <= radius
    }


def _centre(board: Board) -> set[Cell]:
    mid = (board.size - 1) / 2
    span = max(1, board.size // 4)
    return {
        (r, c)
        for r in range(board.size)
        for c in range(board.size)
        if abs(r - mid) <= span and abs(c - mid) <= span
    }


def _edge(board: Board) -> set[Cell]:
    last = board.size - 1
    return {
        (r, c)
        for r in range(board.size)
        for c in range(board.size)
        if r in (0, last) or c in (0, last)
    }


def _corners(board: Board) -> set[Cell]:
    last = board.size - 1
    reach = max(1, board.size // 3)
    out: set[Cell] = set()
    for corner in ((0, 0), (0, last), (last, 0), (last, last)):
        out |= _disc(board, corner, radius=reach - 1)
    return out


def _half(board: Board, bearing: tuple[int, int]) -> set[Cell]:
    """The half of the board a bearing points into, excluding the middle band."""
    d_row, d_col = bearing
    mid = (board.size - 1) / 2
    out: set[Cell] = set()
    for row in range(board.size):
        for col in range(board.size):
            score = d_row * (row - mid) + d_col * (col - mid)
            if score > 0:
                out.add((row, col))
    return out
