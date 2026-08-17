"""Exact pursuit solving over the joint (thief, officer) state.

Both brains used to reason about a single move against a frozen snapshot of the
world. That is enough to notice a cell is dangerous *now* and never enough to
notice a cell whose every continuation is dangerous next turn — which is exactly
the trap a good pursuer sets, and exactly how a greedy evader walks into it.

So stop estimating and solve. The joint state is tiny: 49 thief cells x 49
officer cells, under five thousand states, so backward induction over the whole
space costs milliseconds and answers the only question that matters — *from
here, for how many plies can the thief be kept alive against best play?*

The representation is what makes it cheap. For each thief cell we keep a single
integer whose bits are the officer cells the thief survives, so one ply of the
induction is a few dozen big-integer operations rather than a quarter of a
million Python-level state visits.

Two deliberate simplifications, both conservative for the thief:

* **Future barriers are not searched.** Putting the wall set in the state would
  make the space exponential. We re-solve each turn against the walls that
  exist, which is exact for the board in front of us and simply re-derived when
  a new wall appears.
* **The officer is assumed perfect** — it always plays the reply that hurts
  most. A thief that survives this analysis survives a weaker officer too.
"""

from p2p_chase.constants import Cell
from p2p_chase.domain.board import Board

#: Plies beyond which safety on an open board is effectively always attainable.
#: Deeper solving spends turn budget re-confirming what shallower depths settled;
#: callers may raise it once the board is heavily walled.
DEFAULT_HORIZON = 12


class SafetyTable:
    """Which (thief, officer) pairs the thief survives, by ply depth."""

    def __init__(self, size: int, masks: list[list[int]], replies: list) -> None:
        self._size = size
        # _masks[h][t] has bit c set when a thief on `t`, officer on `c`, thief
        # to move, survives at least `h` further plies.
        self._masks = masks
        # _replies[h][t] is the same question one half-move later: the thief has
        # already settled on `t` and the officer is about to reply. This is the
        # layer a brain actually needs, because a brain chooses a destination and
        # then has to live with whatever the officer does next.
        self._replies = replies

    @property
    def depth(self) -> int:
        return len(self._masks) - 1

    def survives(self, thief: Cell, officer: Cell, plies: int) -> bool:
        """Can the thief hold out ``plies`` more, with the thief to move?"""
        if plies <= 0:
            return True
        depth = min(plies, self.depth)
        return bool(self._masks[depth][_index(self._size, thief)] >> _index(self._size, officer) & 1)

    def survivable_plies(self, thief: Cell, officer: Cell) -> int:
        """The deepest ply count the thief is provably safe to, from this state."""
        return self._deepest(self._masks, thief, officer)

    def survives_after_move(self, target: Cell, officer: Cell, plies: int) -> bool:
        """Having just moved to ``target``, does the thief survive ``plies`` more?"""
        if plies <= 0:
            return True
        depth = min(plies, self.depth)
        index = _index(self._size, target)
        return bool(self._replies[depth][index] >> _index(self._size, officer) & 1)

    def plies_after_move(self, target: Cell, officer: Cell) -> int:
        """How deep ``target`` is provably safe to, with the officer to reply.

        The graceful-degradation number: when nothing is safe to the full
        horizon, a brain still needs to know which losing move loses slowest.
        """
        return self._deepest(self._replies, target, officer)

    def _deepest(self, layers: list, thief: Cell, officer: Cell) -> int:
        index = _index(self._size, thief)
        bit = _index(self._size, officer)
        for depth in range(self.depth, 0, -1):
            if layers[depth][index] >> bit & 1:
                return depth
        return 0


def solve(
    board: Board,
    barriers,
    horizon: int = DEFAULT_HORIZON,
    *,
    stay_allowed: bool = True,
) -> SafetyTable:
    """Backward-induct the joint state space for ``horizon`` plies."""
    size = board.size
    blocked = frozenset(barriers)
    steps = {
        _index(size, cell): _reachable_mask(board, cell, blocked, stay_allowed)
        for cell in _open_cells(size, blocked)
    }
    total = size * size
    everywhere = (1 << total) - 1
    # A thief with no *step* available is captured by enclosure under rule 47,
    # and STAY does not rescue it — `OwnGameState.is_immobilised` counts only
    # directional moves. Reading that the other way round would be the worst
    # possible error here: the thief would walk into a one-cell pocket, find it
    # could stand there indefinitely with the officer unable to enter, and call
    # a completed capture perfect safety.
    mobile = {
        _index(size, cell)
        for cell in _open_cells(size, blocked)
        if board.neighbors(cell, blocked)
    }
    # Depth 0: alive anywhere the thief can still move and the officer is not
    # already standing. Sharing a cell is the one state no depth ever rescues.
    alive = [
        everywhere & ~(1 << index) if index in mobile else 0
        for index in range(total)
    ]

    masks, replies = [alive], [alive]
    for _ in range(horizon):
        reply = _officer_reply(total, steps, masks[-1])
        replies.append(reply)
        masks.append(_thief_move(total, steps, reply))
    return SafetyTable(size, masks, replies)


def _thief_move(total: int, steps: dict[int, int], after_move: list[int]) -> list[int]:
    """The thief needs only *one* destination that survives the officer's reply,
    so the officer cells it escapes from are the union over its options."""
    result = [0] * total
    for index, options in steps.items():
        escape = 0
        for target in _bits(options):
            escape |= after_move[target]
        result[index] = escape
    return result


def _officer_reply(total: int, steps: dict[int, int], previous: list[int]) -> list[int]:
    """With the thief settled on a cell, which officer cells still leave it safe.

    The officer needs only *one* move that hurts, so the thief is safe here only
    where **every** officer reply leaves it safe. That universal quantifier is a
    subset test: the officer's whole reachable set must land inside the officer
    cells the thief already survives. This is the half of the induction that
    does the work, and the half a one-move heuristic can never express.
    """
    result = [0] * total
    for thief in range(total):
        if thief not in steps:
            continue
        # Landing on the thief is a capture, so it is never an allowed reply.
        allowed = previous[thief] & ~(1 << thief)
        survivors = 0
        for officer, replies in steps.items():
            if not replies & ~allowed:
                survivors |= 1 << officer
        # An officer already sharing the cell has captured, whatever its replies
        # look like. The subset test alone does not say so: where STAY is not in
        # the move set, an officer standing on the thief must step away, and
        # every one of those steps passes.
        result[thief] = survivors & ~(1 << thief)
    return result


def _open_cells(size: int, blocked) -> list[Cell]:
    return [
        (row, col)
        for row in range(size)
        for col in range(size)
        if (row, col) not in blocked
    ]


def _reachable_mask(board: Board, cell: Cell, blocked, stay_allowed: bool) -> int:
    size = board.size
    mask = 1 << _index(size, cell) if stay_allowed else 0
    for neighbour in board.neighbors(cell, blocked):
        mask |= 1 << _index(size, neighbour)
    return mask


def _index(size: int, cell: Cell) -> int:
    return cell[0] * size + cell[1]


def _bits(mask: int):
    """Yield the set bit positions of ``mask``, lowest first."""
    while mask:
        low = mask & -mask
        yield low.bit_length() - 1
        mask ^= low
