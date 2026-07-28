"""Board geometry: bounds, legal steps, distance, and connectivity.

The board is deliberately *stateless with respect to the match*. It answers
geometric questions about an ``N x N`` grid given a barrier set; who stands
where is the private business of :mod:`p2p_chase.domain.own_state`. Keeping the
two apart is what lets the strategy layer ask hypothetical questions ("if I
sealed this cell, how much room would the thief have left?") without mutating
anything.
"""

from collections import deque
from collections.abc import Iterable

from p2p_chase.constants import DELTAS, ORTHOGONAL, Cell, Direction


class Board:
    """An ``N x N`` grid with a configurable set of legal step directions."""

    def __init__(self, size: int, moves: Iterable[Direction] | None = None) -> None:
        if size < 2:
            raise ValueError(f"Board size must be at least 2, got {size}")
        self.size = size
        self._moves: tuple[Direction, ...] = tuple(moves) if moves else ORTHOGONAL

    @property
    def moves(self) -> tuple[Direction, ...]:
        """The legal step directions, in a stable order (determinism matters:
        both peers must reproduce the same move list during an audit)."""
        return self._moves

    @property
    def diagonal(self) -> bool:
        """True when the negotiated move set includes any diagonal step."""
        return any(DELTAS[d][0] and DELTAS[d][1] for d in self._moves)

    @property
    def cells(self) -> int:
        return self.size * self.size

    def in_bounds(self, cell: Cell) -> bool:
        row, col = cell
        return 0 <= row < self.size and 0 <= col < self.size

    def distance(self, a: Cell, b: Cell) -> int:
        """Steps needed on an empty board.

        Manhattan for orthogonal movement — an admissible (never-overestimating)
        heuristic there — and Chebyshev when diagonals are enabled.
        """
        if self.diagonal:
            return max(abs(a[0] - b[0]), abs(a[1] - b[1]))
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def step(
        self, origin: Cell, direction: Direction | None, barriers: Iterable[Cell] | None = None
    ) -> Cell | None:
        """The cell reached from ``origin``, or ``None`` if the step is illegal.

        A step is illegal when the direction is outside the negotiated move set,
        when it would leave the board, or when the target cell is sealed.
        """
        if direction is None or direction not in self._moves:
            return None
        d_row, d_col = DELTAS[direction]
        target = (origin[0] + d_row, origin[1] + d_col)
        if not self.in_bounds(target):
            return None
        if barriers and target in set(barriers):
            return None
        return target

    def legal_moves(
        self, origin: Cell, barriers: Iterable[Cell] | None = None
    ) -> list[tuple[Direction, Cell]]:
        """Every ``(direction, target)`` reachable in one step from ``origin``."""
        blocked = set(barriers) if barriers else set()
        found = []
        for direction in self._moves:
            target = self.step(origin, direction, blocked)
            if target is not None:
                found.append((direction, target))
        return found

    def neighbors(self, cell: Cell, barriers: Iterable[Cell] | None = None) -> list[Cell]:
        return [target for _, target in self.legal_moves(cell, barriers)]

    def reachable(
        self, origin: Cell, barriers: Iterable[Cell] | None = None, limit: int | None = None
    ) -> set[Cell]:
        """Breadth-first flood fill: every cell reachable from ``origin``.

        ``limit`` caps the search depth, which is how the strategy layer asks
        "where could the opponent possibly be in the next *k* turns?" without
        paying for a full-board fill every time.
        """
        blocked = set(barriers) if barriers else set()
        if origin in blocked:
            return set()
        seen = {origin}
        frontier = deque([(origin, 0)])
        while frontier:
            cell, depth = frontier.popleft()
            if limit is not None and depth >= limit:
                continue
            for target in self.neighbors(cell, blocked):
                if target not in seen:
                    seen.add(target)
                    frontier.append((target, depth + 1))
        return seen

    def shortest_path_length(
        self, origin: Cell, target: Cell, barriers: Iterable[Cell] | None = None
    ) -> int | None:
        """True walking distance around barriers, or ``None`` if unreachable.

        Manhattan distance ignores walls; once the officer starts building them,
        only this number tells you who really gets there first.
        """
        blocked = set(barriers) if barriers else set()
        if origin == target:
            return 0
        if target in blocked or origin in blocked:
            return None
        seen = {origin}
        frontier = deque([(origin, 0)])
        while frontier:
            cell, depth = frontier.popleft()
            for nxt in self.neighbors(cell, blocked):
                if nxt == target:
                    return depth + 1
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append((nxt, depth + 1))
        return None
