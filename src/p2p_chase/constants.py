"""Immutable vocabulary of the game: roles, actions, directions, phases.

These are *not* configuration. Every tunable number lives in ``config/`` and is
reached through :class:`p2p_chase.shared.config.ConfigManager`; what lives here
is the type system the rest of the package speaks (submission guidelines §7.2).
"""

from enum import StrEnum
from typing import Final

Cell = tuple[int, int]


class Role(StrEnum):
    """Which side a peer plays in a given sub-game. Roles alternate across a series."""

    THIEF = "thief"
    POLICE = "police"

    @property
    def opponent(self) -> "Role":
        return Role.POLICE if self is Role.THIEF else Role.THIEF


class MoveType(StrEnum):
    """The actions a peer may take in one turn.

    ``BARRIER`` is police-only: the officer forgoes movement and seals a cell at
    distance one instead (book ch.3, "the barrier rule").
    """

    MOVE = "MOVE"
    BARRIER = "BARRIER"
    HOLD = "HOLD"


class Direction(StrEnum):
    """Compass directions. The book's default move set is the four orthogonals;
    the diagonals exist only so a negotiated variant board can enable them."""

    N = "N"
    NE = "NE"
    E = "E"
    SE = "SE"
    S = "S"
    SW = "SW"
    W = "W"
    NW = "NW"


#: (row_delta, col_delta) per direction. Row index grows downward (south),
#: matching ``axis_origin_corner = "top-left"``.
DELTAS: Final[dict[Direction, tuple[int, int]]] = {
    Direction.N: (-1, 0),
    Direction.NE: (-1, 1),
    Direction.E: (0, 1),
    Direction.SE: (1, 1),
    Direction.S: (1, 0),
    Direction.SW: (1, -1),
    Direction.W: (0, -1),
    Direction.NW: (-1, -1),
}

#: The book's default (and this project's) move set: four orthogonals, no diagonals.
ORTHOGONAL: Final[tuple[Direction, ...]] = (
    Direction.N,
    Direction.S,
    Direction.E,
    Direction.W,
)

#: Tokens that mean "stand still" in a configured ``move_set``. They are legal
#: actions but not board steps, so the board never needs to know about them.
STAY_TOKENS: Final[frozenset[str]] = frozenset({"STAY", "HOLD"})


class Intent(StrEnum):
    """Whether the natural-language hint attached to a move is honest.

    The peer must commit to this flag *before* the opponent sees the hint, so it
    can never claim after the fact that a lie was "meant" as truth (book ch.5).
    """

    TRUTH = "truth"
    LIE = "lie"


class Outcome(StrEnum):
    """How one sub-game ended. Anything other than CAPTURE/SURVIVAL scores 0-0."""

    CAPTURE = "capture"
    SURVIVAL = "survival"
    TIMEOUT = "timeout"
    TAMPER_FORFEIT = "tamper_forfeit"
    STOPPED = "stopped"


#: Cryptographic nonce length in bytes for commit-reveal sealing (book ch.5).
NONCE_BYTES: Final[int] = 16

#: Fixed protocol texts. Not tunables — the opponent parses none of them, but a
#: caught thief must say something, and silence must be distinguishable.
FINAL_CAUGHT_HINT: Final[str] = "You got me."
NO_HINT_PLACEHOLDER: Final[str] = "(silence)"
