"""Barrier planning: spending a scarce, irreversible resource well.

The officer's asymmetric power is that it can rebuild the board — fourteen times,
permanently, and only by giving up a turn each time. That makes every wall a
three-way trade: a turn not spent closing distance, one of fourteen barriers gone
for good, and a permanent change to the graph that helps *whoever it helps*.

The naive valuation fails badly, and it is worth being explicit about why. On an
open board, sealing one cell removes exactly one cell from the thief's region, so
a planner that demands a large immediate gain never builds anything and the
officer's defining ability goes unused for the whole match. Yet walls plainly do
win games — because their value is **structural and cumulative**, not immediate.
A cell is worth sealing when it:

* removes cells outright (rare early, decisive late);
* **anchors** — touches an existing wall or the board edge, so segments grow into
  barriers rather than scattering as useless isolated blocks;
* is a **cut vertex**, where one cell severs a corridor; or
* probably has the thief standing on it, since sealing an occupied cell is
  itself a capture (mandatory rule 46).

Against that we hold three vetoes: never wall ourselves away from the thief,
never shrink our own region below a floor, and keep a reserve for the endgame,
when the thief's region is small enough that a single cell can halve it.
"""

from dataclasses import dataclass

from p2p_chase.constants import Cell, Direction
from p2p_chase.domain.board import Board
from p2p_chase.strategy import reachability


@dataclass
class BarrierPlan:
    """A candidate wall and the case for building it."""

    direction: Direction | None
    cell: Cell
    cells_removed: float        # immediate shrink of the thief's expected region
    value: float                # structural worth, the number we actually compare
    thief_region_after: float
    viable: bool
    rationale: str


def plan_barrier(
    board: Board,
    position: Cell,
    barriers: set[Cell],
    belief_cells: list[tuple[Cell, float]],
    *,
    anchor_bonus: float = 1.2,
    cut_bonus: float = 6.0,
    occupancy_bonus: float = 12.0,
    own_region_floor: float = 0.25,
) -> BarrierPlan | None:
    """The most valuable wall available this turn, or ``None`` if none is safe."""
    if not belief_cells:
        return None
    baseline = reachability.expected_region_size(board, belief_cells, barriers | {position})
    belief = dict(belief_cells)
    best: BarrierPlan | None = None

    for direction, cell in board.legal_moves(position, barriers):
        plan = _evaluate(
            board, position, barriers, belief_cells, direction, cell, baseline,
            belief.get(cell, 0.0), anchor_bonus, cut_bonus, occupancy_bonus, own_region_floor,
        )
        if plan.viable and (best is None or plan.value > best.value):
            best = plan
    return best


def _evaluate(
    board: Board, position: Cell, barriers: set[Cell], belief_cells, direction, cell: Cell,
    baseline: float, occupancy: float, anchor_bonus: float, cut_bonus: float,
    occupancy_bonus: float, own_region_floor: float,
) -> BarrierPlan:
    """Simulate sealing ``cell`` and price what it actually buys."""
    after = barriers | {cell}
    thief_region = reachability.expected_region_size(board, belief_cells, after | {position})
    removed = baseline - thief_region

    anchors = _anchors(board, cell, barriers)
    cut = reachability.is_cut_vertex(board, cell, barriers)
    value = (
        removed
        + anchor_bonus * anchors
        + (cut_bonus if cut else 0.0)
        + occupancy_bonus * occupancy
    )

    distances = reachability.distance_map(board, position, after)
    reachable_mass = sum(p for target, p in belief_cells if target in distances or target == cell)
    own_region = reachability.region_size(board, position, after)
    viable = reachable_mass > 0.5 and own_region >= own_region_floor * board.cells

    return BarrierPlan(
        direction=direction,
        cell=cell,
        cells_removed=removed,
        value=value,
        thief_region_after=thief_region,
        viable=viable,
        rationale=(
            f"seal {cell}: thief room {baseline:.1f}->{thief_region:.1f}, "
            f"anchors={anchors}{', CUT' if cut else ''}"
            f"{f', p(occupied)={occupancy:.2f}' if occupancy > 0.05 else ''}, "
            f"own room {own_region}"
        ),
    )


#: What one side of board edge is worth relative to one side of real wall.
#: Not zero — a fence does have to start somewhere, and the rim is where a
#: segment can be closed off cheaply — but nowhere near equal, see below.
_EDGE_ANCHOR = 0.25


def _anchors(board: Board, cell: Cell, barriers: set[Cell]) -> float:
    """How strongly this cell continues an existing structure.

    Walls and board edges are *not* interchangeable here, though both stop
    movement. Joining a wall extends something we built for a purpose; abutting
    the rim extends a boundary that was always there and constrains the thief no
    more than before. Counting them equally makes every perimeter cell look like
    a two-anchor bargain, which is exactly how this officer once spent five
    barriers fencing the bottom row while the thief ran free in the middle: the
    thief's room fell by one cell per wall and the pursuit distance *rose*.
    """
    walls = 0
    edges = 0
    for direction in board.moves:
        neighbour = board.step(cell, direction)
        if neighbour is None:
            edges += 1
        elif neighbour in barriers:
            walls += 1
    return walls + _EDGE_ANCHOR * edges


def should_spend(
    *, plan: BarrierPlan, barriers_left: int, steps_remaining: int, total_steps: int,
    expected_distance: float, board_size: int, reserve: int, threshold: float,
) -> bool:
    """Is now the moment to give up a turn and build?

    Two forces set the bar. **Proximity**: when the thief is close, a turn spent
    building is a turn not spent closing, so the bar rises steeply. **The clock**:
    as the survival threshold approaches, an uncaught thief is a loss anyway, so
    the bar falls and the reserve is released.
    """
    if barriers_left <= 0 or not plan.viable:
        return False

    # A wall can only be placed beside us, so it constrains the thief only when
    # the thief is near enough that our neighbourhood is also its neighbourhood.
    # This is the reverse of the rule that lost us three sub-games: that version
    # refused to build while close and built while far, so the officer spent five
    # barriers fencing an empty edge and let the pursuit distance double.
    if expected_distance > board_size * 0.6:
        return False

    urgency = 1.0 - min(1.0, max(0, steps_remaining) / max(1, total_steps))
    bar = threshold * (1.4 - 0.7 * urgency)
    if barriers_left <= reserve and urgency < 0.6:
        bar *= 2.0  # the reserve is for the endgame; early raids on it must pay
    return plan.value >= bar
