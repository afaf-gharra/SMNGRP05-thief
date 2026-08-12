"""Reading the opponent's cell out of the scent field it is obliged to send.

The pheromone model is agreed and signed, which means its consequences are agreed
too. Deposits merge by maximum and the whole field decays by ``rho`` each turn, so
a received grid always peaks on the cell the opponent is standing on right now,
with its recent path trailing behind at ``peak * (1 - rho)^k``. The sender cannot
suppress the peak without breaking the model it signed, and it cannot fake one
without producing a field that contradicts the path it must reveal at the audit.

That makes the peak a very strong signal — but not one to take on faith. A cell is
accepted only if it is consistent with things the opponent does not control:

* the **signed start cell**, which both peers hold in ``game.json``;
* **one step per turn**, over the barrier graph as it stands;
* the **public barrier set** — nobody stands inside a wall.

A field that fails those checks is not noise, it is a claim the sender will not be
able to justify against its own revealed record. We stop believing it for the rest
of the sub-game and say so in the report, rather than quietly letting a doctored
field steer us.
"""

from dataclasses import dataclass

from p2p_chase.constants import Cell
from p2p_chase.domain.board import Board
from p2p_chase.domain.smell import parse_cell


@dataclass
class Decoded:
    """Where the field says the opponent is, and whether we still believe it."""

    cell: Cell | None
    trusted: bool
    reason: str = ""


def peak_cell(cells: dict[str, float], board: Board) -> Cell | None:
    """The unique hottest on-board cell in a received field, or ``None``.

    Ties are broken by cell order so that two peers replaying the same log reach
    the same answer; an ambiguous peak is weak evidence but never a crash.
    """
    best: Cell | None = None
    best_value = 0.0
    for key, value in cells.items():
        cell = parse_cell(key)
        if cell is None or not board.in_bounds(cell):
            continue
        reading = float(value)
        if reading > best_value or (reading == best_value and best is not None and cell < best):
            best, best_value = cell, reading
    return best if best_value > 0.0 else None


def decode_position(
    cells: dict[str, float],
    board: Board,
    barriers: set[Cell],
    previous: Cell | None,
    expected_start: Cell | None = None,
) -> Decoded:
    """Read the opponent's cell from its scent field, checking it against geometry."""
    cell = peak_cell(cells, board)
    if cell is None:
        return Decoded(None, True, "no scent received")

    if cell in barriers:
        return Decoded(None, False, f"peak {cell} is inside a barrier")

    if previous is None:
        # The opponent moves and *then* deposits, so the first field we ever see
        # peaks on the cell it moved to -- one step from the signed start, not on
        # it. Demanding equality here rejected the opening field of every
        # sub-game and latched distrust before a single turn had been played,
        # silently disabling the tracker for the whole match.
        if expected_start is not None and not _within_one_step(
            board, cell, expected_start, barriers
        ):
            return Decoded(
                None, False,
                f"first peak {cell} is not reachable in one step from the "
                f"signed start {expected_start}",
            )
        return Decoded(cell, True)

    if not _within_one_step(board, cell, previous, barriers):
        return Decoded(None, False, f"peak jumped {previous} -> {cell} in one turn")

    return Decoded(cell, True)


def _within_one_step(board: Board, cell: Cell, origin: Cell, barriers: set[Cell]) -> bool:
    """Could someone standing on ``origin`` be on ``cell`` after one move?

    Staying put counts: ``STAY`` is in the agreed move set.
    """
    return cell == origin or cell in board.neighbors(origin, barriers)


class ScentTracker:
    """Follows the opponent across a sub-game, latching distrust once broken.

    Distrust is deliberately sticky. A peer whose field has already contradicted
    the geometry once has shown the field is not being produced by the agreed
    model, and nothing later in the same sub-game makes that less true.
    """

    def __init__(self, board: Board, expected_start: Cell | None = None) -> None:
        self._board = board
        self._expected_start = expected_start
        self.cell: Cell | None = None
        self.trusted = True
        self.failure: str = ""

    def update(self, cells: dict[str, float], barriers: set[Cell]) -> Decoded:
        if not self.trusted:
            return Decoded(None, False, self.failure)
        result = decode_position(
            cells, self._board, barriers, self.cell, self._expected_start
        )
        if not result.trusted:
            self.trusted = False
            self.failure = result.reason
            return result
        if result.cell is not None:
            self.cell = result.cell
        return result
