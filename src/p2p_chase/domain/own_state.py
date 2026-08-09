"""``OwnGameState`` — everything one peer truthfully knows about *itself*.

There is no shared board and no referee. Each peer is authoritative only for its
own position, its visited set and (as police) its barrier budget. Barriers the
opponent declares are folded in as they arrive, because a barrier is public by
rule: it blocks both sides and must be announced truthfully (mandatory rules
15-16).
"""

from p2p_chase.constants import Cell, Direction, MoveType, Role
from p2p_chase.domain.board import Board

#: The token a stationary turn takes on the wire. The agreed ``move_set`` is the
#: authority on what may appear in a sealed ``move`` field, and it names exactly
#: ``N/S/E/W/STAY`` — so an internal action name like ``BARRIER`` or ``HOLD``
#: must never travel there. A stricter opponent replays the sealed moves against
#: the signed move set and refuses to counter-sign anything outside it.
STATIONARY = "STAY"


def wire_move(move_type: MoveType, direction: Direction | None) -> str:
    """The agreed-move-set token for an action, as it must appear when sealed.

    Placing a barrier costs the officer its movement, so it seals as ``STAY``;
    where the wall went is carried by ``barrier_placed``, not smuggled into the
    move field.
    """
    if move_type is MoveType.MOVE and direction is not None:
        return direction.value
    return STATIONARY


class OwnGameState:
    """One peer's private truth plus its per-step move log."""

    def __init__(
        self, role: Role, start: Cell, board_size: int, move_set: list[str] | None = None
    ) -> None:
        from p2p_chase.domain.moveset import directions_from_move_set

        self.role = role
        self.board = Board(board_size, moves=directions_from_move_set(move_set))
        self.can_stay = _stay_allowed(move_set)
        self.position: Cell = tuple(start)  # type: ignore[assignment]
        self.visited: set[Cell] = {self.position}
        self.barriers: set[Cell] = set()  # mine + every barrier the opponent declared
        self.my_barriers = 0
        self.step_number = 0
        self.log: list[dict] = []

    @property
    def unique_cells(self) -> int:
        return len(self.visited)

    @property
    def barriers_left(self) -> int:
        return max(0, self._quota - self.my_barriers)

    def set_quota(self, quota: int) -> None:
        """Record the negotiated barrier quota so ``barriers_left`` can report it."""
        self._quota = quota

    _quota = 0

    def note_barrier(self, cell: Cell) -> None:
        """Record a barrier the opponent declared: impassable for both of us."""
        self.barriers.add(tuple(cell))  # type: ignore[arg-type]

    def is_immobilised(self) -> bool:
        """True when no legal step remains from my cell.

        For a thief this is terminal: the book counts a thief walled in with no
        legal move as captured, exactly as if the officer had stepped onto it
        (mandatory rule 47). Standing still does not save it — being sealed in is
        the capture.
        """
        return not self.board.legal_moves(self.position, self.barriers)

    def apply_move(
        self, move_type: MoveType, direction: Direction | None, barriers_max: int = 0
    ) -> bool:
        """Apply my own action, returning ``False`` and changing nothing if illegal.

        Legality is enforced locally *and* by the opponent, so an illegal action
        is never merely impolite — it is a technical loss waiting to be proven at
        the audit. We therefore refuse it here rather than transmit it.
        """
        placed: Cell | None = None
        if move_type is MoveType.BARRIER:
            placed = self._place_barrier(direction, barriers_max)
            if placed is None:
                return False
        elif move_type is MoveType.MOVE:
            target = self.board.step(self.position, direction, self.barriers)
            if target is None:
                return False
            self.position = target
            self.visited.add(target)
        elif move_type is MoveType.HOLD and not self.can_stay:
            return False
        self.step_number += 1
        self.log.append(
            {
                "step": self.step_number,
                "position": list(self.position),
                "move": f"{move_type.value}:{direction.value if direction else '-'}",
                "wire_move": wire_move(move_type, direction),
                "unique_cells": self.unique_cells,
                "barrier": list(placed) if placed else None,
            }
        )
        return True

    def _place_barrier(self, direction: Direction | None, barriers_max: int) -> Cell | None:
        """Seal a cell within one step of me. Police only, quota-limited, irreversible.

        ``direction is None`` means "seal the cell I am standing on", which the
        book permits (the officer's own cell is at distance zero) and which the
        endgame squeeze uses to plug the last hole in a wall.
        """
        if self.role is not Role.POLICE:
            return None
        if self.my_barriers >= barriers_max:
            return None
        target = self.position if direction is None else self.board.step(
            self.position, direction, self.barriers
        )
        if target is None or target in self.barriers:
            return None
        self.barriers.add(target)
        self.my_barriers += 1
        return target

    def last_barrier(self) -> Cell | None:
        """The cell sealed on my most recent turn, if that turn was a barrier."""
        if self.log and self.log[-1]["barrier"]:
            row, col = self.log[-1]["barrier"]
            return (row, col)
        return None


def _stay_allowed(move_set: list[str] | None) -> bool:
    """Whether the negotiated move set permits standing still."""
    from p2p_chase.constants import STAY_TOKENS

    if not move_set:
        return True
    return any(str(token).strip().upper() in STAY_TOKENS for token in move_set)
