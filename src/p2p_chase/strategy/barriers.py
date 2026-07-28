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


def _anchors(board: Board, cell: Cell, barriers: set[Cell]) -> int:
    """How many sides of this cell already abut a wall or the board edge.

    This is what turns scattered blocks into a fence. A cell with two anchors
    continues a line; a cell with none starts an island the thief walks around.
    """
    count = 0
    for direction in board.moves:
        neighbour = board.step(cell, direction)
        if neighbour is None or neighbour in barriers:
            count += 1
    return count


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

    closing_in = expected_distance <= 2.0
    if closing_in:
        # Within striking distance, only a wall that is effectively a capture
        # or a genuine corridor cut is worth stopping for.
        return plan.value >= threshold * 3.0

    urgency = 1.0 - min(1.0, max(0, steps_remaining) / max(1, total_steps))
    bar = threshold * (1.6 - 0.8 * urgency)
    if barriers_left <= reserve and urgency < 0.6:
        bar *= 2.0  # the reserve is for the endgame; early raids on it must pay
    return plan.value >= bar
