"""Stigmergic scent trails: emission, decay, and the field a peer can read.

Both sides emit, both sides read — the mechanism is perfectly symmetric. A peer
cannot plant a false trail anywhere it has not physically been, which is what
makes the scent field the one *unforgeable* witness in a game where every spoken
word may be a lie (book ch.4).

Decay follows the book's formula, applied to the whole field once per full turn:

    tau(t+1) = max(0, (1 - rho) * tau(t) + delta_tau)

Note this is **multiplicative**, not a flat subtraction. With ``rho = 0.10`` a
single deposit keeps roughly 0.9**t of its strength, crossing half-peak near
turn 7 — the six-to-seven-turn readable trail the book describes. A subtractive
decay would empty the board in nine turns and change the game materially; where
the course's reference simulator subtracts, we follow the book, which is binding.
"""

import math

from p2p_chase.constants import Cell

#: Falloff shapes for the emission window. ``linear`` is the interoperable
#: default (it is what the reference simulator broadcasts, so a stock opponent's
#: numbers and ours are on the same scale); ``gaussian`` reproduces the smooth
#: hill drawn in the book's figure 4 and may be selected by mutual agreement.
LINEAR = "linear"
GAUSSIAN = "gaussian"
#: exp(-GAUSSIAN_K * d^2) reproduces the book's figure to two decimal places.
GAUSSIAN_K = 0.375


class SmellField:
    """Scent intensities over the whole board as known to one peer."""

    def __init__(
        self,
        board_size: int,
        grid_size: int,
        decay: float,
        min_center: float = 0.0,
        falloff: str = LINEAR,
    ) -> None:
        self._board_size = board_size
        self._grid_size = grid_size
        self._decay = decay
        self._min_center = min_center
        self._falloff = falloff
        self._values: dict[Cell, float] = {}

    def emission(self, center: Cell, intensity: float) -> dict[Cell, float]:
        """The ``grid_size x grid_size`` window this peer would lay around ``center``.

        Pure: returns the window without touching the field, so the strategy
        layer can ask "how loudly would I be shouting if I stood there?" before
        committing to a move.
        """
        half = self._grid_size // 2
        window: dict[Cell, float] = {}
        for d_row in range(-half, half + 1):
            for d_col in range(-half, half + 1):
                cell = (center[0] + d_row, center[1] + d_col)
                if not self._on_board(cell):
                    continue
                window[cell] = round(self._value_at(intensity, d_row, d_col, half), 3)
        return window

    def _value_at(self, intensity: float, d_row: int, d_col: int, half: int) -> float:
        if self._falloff == GAUSSIAN:
            squared = d_row * d_row + d_col * d_col
            return max(0.0, intensity * math.exp(-GAUSSIAN_K * squared))
        chebyshev = max(abs(d_row), abs(d_col))
        return max(0.0, intensity - (intensity / (half + 1)) * chebyshev)

    def _on_board(self, cell: Cell) -> bool:
        return 0 <= cell[0] < self._board_size and 0 <= cell[1] < self._board_size

    def deposit(self, center: Cell, intensity: float) -> None:
        """Lay a fresh window around ``center``, merging by maximum.

        Only the resulting *field* ever crosses the wire, never the centre cell,
        so the opponent receives evidence rather than coordinates.
        """
        if intensity < self._min_center:
            raise ValueError(
                f"Centre intensity {intensity} is below the agreed minimum {self._min_center}"
            )
        for cell, value in self.emission(center, intensity).items():
            self._values[cell] = max(self._values.get(cell, 0.0), value)

    def absorb(self, cells: dict[str, float]) -> None:
        """Merge a received ``{'r,c': intensity}`` map into what I know."""
        for key, value in cells.items():
            cell = parse_cell(key)
            if cell is not None and self._on_board(cell):
                self._values[cell] = max(self._values.get(cell, 0.0), float(value))

    def decay_all(self) -> None:
        """One full turn elapsed: every intensity fades by ``(1 - rho)``."""
        retained = 1.0 - self._decay
        for cell in list(self._values):
            faded = round(max(0.0, self._values[cell] * retained), 4)
            if faded <= 0.0005:
                del self._values[cell]  # drop dead cells so snapshots stay small
            else:
                self._values[cell] = faded

    def intensity_at(self, cell: Cell) -> float:
        return self._values.get(cell, 0.0)

    def total(self) -> float:
        return sum(self._values.values())

    def strongest_cell(self) -> Cell | None:
        """The most fragrant cell — the naive, pre-Bayesian guess at the opponent."""
        if not self._values:
            return None
        cell, value = max(self._values.items(), key=lambda item: (item[1], item[0]))
        return cell if value > 0.0 else None

    def hot_cells(self, threshold: float = 0.0) -> set[Cell]:
        return {cell for cell, value in self._values.items() if value > threshold}

    def snapshot(self) -> dict[str, float]:
        """Serialisable ``{'r,c': intensity}`` copy for the wire, the log and the GUI."""
        return {f"{r},{c}": v for (r, c), v in sorted(self._values.items()) if v > 0.0}


def parse_cell(key: str) -> Cell | None:
    """Parse a ``'r,c'`` wire key, tolerating whitespace and rejecting junk."""
    try:
        row_text, col_text = str(key).split(",")
        return (int(row_text.strip()), int(col_text.strip()))
    except (ValueError, AttributeError):
        return None
