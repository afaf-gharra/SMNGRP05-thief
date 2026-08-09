"""Bayesian belief over the hidden opponent's cell.

Nobody ever sees the opponent. Each peer carries a probability distribution
``b(s) = P(opponent at s | everything I have observed)`` and runs the textbook
recursive filter once per turn:

1. **Predict** — the opponent moved, so push mass along the *legal* steps out of
   every cell. Unlike a blind 3x3 smear this respects barriers and the negotiated
   move set, so mass never leaks through a wall the officer paid for.
2. **Update** — reweight by the likelihood of the scent field we just received,
   then by the likelihood of what the opponent *said*, discounted by how often
   that opponent has been caught lying (see :mod:`p2p_chase.domain.trust`).

Steps 1 and 2 are separate methods on purpose: the strategy layer runs *only*
the prediction step when it wants to reason one move ahead without pretending to
have observed anything yet.
"""

from collections.abc import Iterable

from p2p_chase.constants import Cell
from p2p_chase.domain.board import Board
from p2p_chase.domain.smell import parse_cell

_EPSILON = 1e-12


class BeliefGrid:
    """A normalised probability grid over the board."""

    def __init__(self, board: Board, smell_trust: float = 4.0) -> None:
        self._board = board
        self._smell_trust = smell_trust
        self._size = board.size
        uniform = 1.0 / board.cells
        self._probs: list[list[float]] = [[uniform] * self._size for _ in range(self._size)]

    # ---------------------------------------------------------------- predict

    def predict(self, barriers: Iterable[Cell] | None = None, stay_allowed: bool = True) -> None:
        """Motion model: spread each cell's mass over the moves available from it."""
        blocked = set(barriers) if barriers else set()
        fresh = [[0.0] * self._size for _ in range(self._size)]
        for row in range(self._size):
            for col in range(self._size):
                mass = self._probs[row][col]
                if mass < _EPSILON or (row, col) in blocked:
                    continue
                targets = self._board.neighbors((row, col), blocked)
                if stay_allowed or not targets:
                    targets = [(row, col), *targets]
                share = mass / len(targets)
                for t_row, t_col in targets:
                    fresh[t_row][t_col] += share
        self._probs = fresh
        self._normalise()

    # ----------------------------------------------------------------- update

    def observe_smell(self, cells: dict[str, float]) -> None:
        """Reweight by the received scent field.

        Likelihood ``P(field | opponent here) = 1 + w * intensity``: a cell that
        reeks is more consistent with the opponent standing there, and a cell
        with no reading is not *impossible*, merely unremarkable. Multiplying
        rather than replacing is what keeps this a filter and not a fresh guess.
        """
        if not cells:
            return
        for key, value in cells.items():
            cell = parse_cell(key)
            if cell is None or not self._board.in_bounds(cell):
                continue
            self._probs[cell[0]][cell[1]] *= 1.0 + self._smell_trust * float(value)
        self._normalise()

    def observe_scent_peak(self, cells: dict[str, float], sharpness: float = 16.0) -> None:
        """Reweight by the scent field, taking its *shape* seriously.

        The agreed pheromone model deposits by maximum and decays multiplicatively,
        so the field carries far more than "somewhere warm": the opponent's current
        cell holds the peak, the cell it left last turn holds ``peak * (1 - rho)``,
        and so on back along the trail. The freshest reading is therefore a unique
        maximum, and the whole path is ordered behind it.

        :meth:`observe_smell`'s gentle ``1 + w*I`` cannot exploit that. It separates
        the true cell from a one-turn-old cell by about 1.08 to 1, while the stale
        cell has been collecting that same small boost every turn since the opponent
        stood there. The compounding wins, and the filter converges on the *start*
        of the trail: measured against a real opponent's path it ended six cells
        adrift, thirty times more confident in a cell abandoned ten moves earlier
        than in the one being stood on.

        Raising the ratio to a power fixes the ordering, but only if the weighting
        covers the *whole board*. Touching just the cells named in the message
        leaves every unscented cell unpenalised, and the prediction step keeps
        refilling that reservoir; measured, that still finishes five cells adrift.
        A cell with no reading is evidence of absence here, not merely an absence
        of evidence, so it is scored as intensity zero like any other.
        """
        if not cells:
            return
        readings: dict[Cell, float] = {}
        for key, value in cells.items():
            cell = parse_cell(key)
            if cell is not None and self._board.in_bounds(cell):
                readings[cell] = float(value)
        peak = max(readings.values(), default=0.0)
        if peak <= 0.0:
            return
        for row in range(self._size):
            for col in range(self._size):
                ratio = readings.get((row, col), 0.0) / peak
                self._probs[row][col] *= ratio**sharpness
        self._normalise()

    def observe_region(self, region: Iterable[Cell], trust: float) -> None:
        """Reweight by a *claimed* region, discounted by how credible the talker is.

        ``trust`` is ``P(this hint is honest)``. At 0.5 the update is a no-op, so
        a peer that has learned nothing about its opponent's honesty is not
        pushed around by talk. Above 0.5 the named region gains mass; below it,
        the region loses mass and the rest of the board gains — a hint from a
        known liar is still information, just inverted.
        """
        named = {cell for cell in region if self._board.in_bounds(cell)}
        if not named or abs(trust - 0.5) < 1e-6:
            return
        gain = 1.0 + 2.0 * (trust - 0.5)
        loss = max(_EPSILON, 2.0 - gain)
        for row in range(self._size):
            for col in range(self._size):
                self._probs[row][col] *= gain if (row, col) in named else loss
        self._normalise()

    def exclude(self, cell: Cell) -> None:
        """Rule a cell out: I am standing here and no capture happened, so it is empty."""
        if self._board.in_bounds(cell):
            self._probs[cell[0]][cell[1]] = 0.0
            self._normalise()

    def collapse_to(self, cell: Cell, confidence: float = 0.97) -> None:
        """Fold in a near-certain sighting: almost all mass on one cell.

        Used when the opponent hands us its exact position — a capture claim can
        only name the cell the officer just stepped onto. We stop just short of a
        point mass so a single spoofed message cannot permanently blind the
        filter: the residual keeps the prediction step able to recover.
        """
        if not self._board.in_bounds(cell):
            return
        spare = (1.0 - confidence) / max(1, self._board.cells - 1)
        self._probs = [[spare] * self._size for _ in range(self._size)]
        self._probs[cell[0]][cell[1]] = confidence
        self._normalise()

    def exclude_all(self, cells: Iterable[Cell]) -> None:
        changed = False
        for cell in cells:
            if self._board.in_bounds(cell):
                self._probs[cell[0]][cell[1]] = 0.0
                changed = True
        if changed:
            self._normalise()

    # ------------------------------------------------------------------ query

    def probability(self, cell: Cell) -> float:
        if not self._board.in_bounds(cell):
            return 0.0
        return self._probs[cell[0]][cell[1]]

    def most_likely(self) -> Cell:
        """``argmax b(s)``, ties broken by cell order so both peers replay identically."""
        best: Cell = (0, 0)
        best_p = -1.0
        for row in range(self._size):
            for col in range(self._size):
                if self._probs[row][col] > best_p:
                    best, best_p = (row, col), self._probs[row][col]
        return best

    def top_cells(self, count: int) -> list[tuple[Cell, float]]:
        """The ``count`` most likely cells, hottest first."""
        flat = [
            ((r, c), self._probs[r][c]) for r in range(self._size) for c in range(self._size)
        ]
        flat.sort(key=lambda item: (-item[1], item[0]))
        return flat[:count]

    def mass_within(self, centre: Cell, radius: int) -> float:
        """How much belief sits within ``radius`` steps of a cell.

        This is the number the officer actually optimises: not "am I near the
        single hottest cell" but "how much of the opponent's probable whereabouts
        am I covering".
        """
        return sum(
            self._probs[r][c]
            for r in range(self._size)
            for c in range(self._size)
            if self._board.distance((r, c), centre) <= radius
        )

    def as_matrix(self) -> list[list[float]]:
        return [row[:] for row in self._probs]

    def _normalise(self) -> None:
        total = sum(sum(row) for row in self._probs)
        if total < _EPSILON:  # everything got ruled out: fall back to ignorance
            uniform = 1.0 / self._board.cells
            self._probs = [[uniform] * self._size for _ in range(self._size)]
            return
        self._probs = [[value / total for value in row] for row in self._probs]
