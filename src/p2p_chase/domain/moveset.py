"""Translate a negotiated ``move_set`` into board directions.

The shared config expresses movement the way two humans would agree on it —
``["N", "S", "E", "W", "STAY"]`` — while the board only understands actual
steps. ``STAY``/``HOLD`` are legal *actions* but not board *directions*, so they
are filtered out here and handled by :class:`~p2p_chase.constants.MoveType`.
"""

from collections.abc import Iterable

from p2p_chase.constants import ORTHOGONAL, STAY_TOKENS, Direction


def directions_from_move_set(move_set: Iterable[str] | None) -> tuple[Direction, ...]:
    """Parse a configured move set, falling back to the book's four orthogonals.

    Unknown tokens are dropped rather than raising: the opponent may legitimately
    propose a move set from a future revision, and the signed-terms check is the
    place where a genuine disagreement is caught, not here.
    """
    if not move_set:
        return ORTHOGONAL
    directions: list[Direction] = []
    for token in move_set:
        name = str(token).strip().upper()
        if name in STAY_TOKENS:
            continue
        try:
            direction = Direction(name)
        except ValueError:
            continue
        if direction not in directions:
            directions.append(direction)
    return tuple(directions) or ORTHOGONAL
