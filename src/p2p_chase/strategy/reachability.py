"""Spatial analysis the tactics are actually built on.

Manhattan distance is the obvious heuristic and it is wrong the moment the first
barrier goes up: two cells one apart on the grid can be twenty steps apart on the
graph. Every judgement in this package therefore uses *graph* quantities —
true shortest paths and connected-region sizes computed by breadth-first search
over the current barrier set.

The two questions that decide the match:

* **How much room does the thief still have?** — the size of the connected
  region it can reach. The officer's whole job is to make that number fall; the
  thief's whole job is to keep it large.
* **Who really gets there first?** — a distance *map* from one cell to every
  other, which the officer weights by its belief to get an expected time-to-catch.
"""

from collections import deque
from collections.abc import Iterable

from p2p_chase.constants import Cell
from p2p_chase.domain.board import Board


def distance_map(
    board: Board, origin: Cell, barriers: Iterable[Cell] | None = None
) -> dict[Cell, int]:
    """True step distance from ``origin`` to every reachable cell."""
    blocked = set(barriers) if barriers else set()
    if origin in blocked:
        return {}
    distances: dict[Cell, int] = {origin: 0}
    frontier = deque([origin])
    while frontier:
        cell = frontier.popleft()
        for nxt in board.neighbors(cell, blocked):
            if nxt not in distances:
                distances[nxt] = distances[cell] + 1
                frontier.append(nxt)
    return distances


def region(board: Board, origin: Cell, barriers: Iterable[Cell] | None = None) -> set[Cell]:
    """The connected component containing ``origin``."""
    return board.reachable(origin, barriers)


def region_size(board: Board, origin: Cell, barriers: Iterable[Cell] | None = None) -> int:
    """How many cells ``origin`` can still reach — the thief's remaining freedom."""
    return len(region(board, origin, barriers))


def expected_region_size(
    board: Board,
    belief_cells: list[tuple[Cell, float]],
    barriers: Iterable[Cell] | None = None,
) -> float:
    """Belief-weighted average of the thief's remaining room.

    The officer does not know where the thief is, so it cannot shrink *the*
    region — only the expected one. Caching per component keeps this affordable:
    the cells sharing a component share an answer.
    """
    blocked = set(barriers) if barriers else set()
    if not any(probability > 0.0 for _cell, probability in belief_cells):
        return float(board.cells)  # we know nothing, so assume the worst

    cache: dict[Cell, int] = {}
    total = 0.0
    weight = 0.0
    for cell, probability in belief_cells:
        if probability <= 0.0 or cell in blocked:
            continue
        if cell not in cache:
            component = region(board, cell, blocked)
            size = len(component)
            for member in component:
                cache[member] = size
        total += probability * cache[cell]
        weight += probability
    # Every cell the thief might be on is walled: it has no room left at all.
    # Falling back to the whole board here would be exactly backwards, and it
    # made the single most valuable wall in the game -- the one sealing the cell
    # the thief is standing on, which rule 46 counts as a capture -- look as
    # though it *enlarged* the thief's region.
    return total / weight if weight else 0.0


def expected_distance(
    distances: dict[Cell, int], belief_cells: list[tuple[Cell, float]], unreachable: int
) -> float:
    """Belief-weighted expected walking distance, charging ``unreachable`` for cut-off cells."""
    total = 0.0
    weight = 0.0
    for cell, probability in belief_cells:
        if probability <= 0.0:
            continue
        total += probability * distances.get(cell, unreachable)
        weight += probability
    return total / weight if weight else float(unreachable)


def exits(board: Board, cell: Cell, barriers: Iterable[Cell] | None = None) -> int:
    """Degree of a cell: how many ways out it has. One means a dead end."""
    return len(board.neighbors(cell, barriers))


def mobility(
    board: Board, cell: Cell, barriers: Iterable[Cell] | None = None, horizon: int = 3
) -> float:
    """How much room ``cell`` has *nearby*, as a fraction of the best a cell could have.

    Region size answers "is there anywhere left to go", which on an open board is
    the same 48/49 everywhere and therefore decides nothing. This answers the
    question that actually kills a thief: "how many places can I be in three
    moves?" A centre cell reaches roughly 25; a corner reaches 10 while still
    reporting full region size and two exits, so neither of the other terms sees
    the trap closing.
    """
    reachable = distance_map(board, cell, barriers)
    near = sum(1 for dist in reachable.values() if 0 < dist <= horizon)
    ceiling = 2 * horizon * (horizon + 1)  # the open-plane diamond around a cell
    return min(1.0, near / ceiling) if ceiling else 0.0


def is_cut_vertex(board: Board, cell: Cell, barriers: Iterable[Cell] | None = None) -> bool:
    """Would sealing ``cell`` split its surroundings into disconnected pieces?

    Cut vertices are where a barrier buys the most: one cell spent, a whole
    corridor severed. Finding them by "remove it and see" is O(V+E) per query,
    which on a 49-cell board is free and far easier to trust than an incremental
    articulation-point algorithm.
    """
    blocked = set(barriers) if barriers else set()
    if cell in blocked:
        return False
    neighbours = board.neighbors(cell, blocked)
    if len(neighbours) < 2:
        return False
    with_wall = blocked | {cell}
    first = region(board, neighbours[0], with_wall)
    return any(other not in first for other in neighbours[1:])


def frontier_cells(
    board: Board, origin: Cell, barriers: Iterable[Cell] | None = None, radius: int = 1
) -> set[Cell]:
    """Cells within ``radius`` steps of ``origin`` — the officer's barrier palette."""
    distances = distance_map(board, origin, barriers)
    return {cell for cell, dist in distances.items() if 0 < dist <= radius}
