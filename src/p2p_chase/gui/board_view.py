"""Canvas rendering for both windows.

One deliberate constraint governs everything here: this widget can only draw
what it is given, and what it is given is *local truth* — my cell, the barriers
I know about, the scent I can smell and the belief I have inferred. The
opponent's true position is not a field it accepts, so no future change to the
live window can accidentally leak it (mandatory rules 8-9).
"""

import tkinter as tk

from p2p_chase.constants import Cell

BACKGROUND = "#12151b"
GRID_LINE = "#2a3040"
BARRIER = "#3a4050"
SELF_FILL = "#4da3ff"
SELF_TEXT = "#04121f"
SCENT = "#2f7d4f"
LABEL = "#8b93a7"


def belief_colour(probability: float, peak: float) -> str:
    """Belief mass as deepening red. Normalised to the peak so a flat, uncertain
    map stays legible instead of rendering as one uniform smear."""
    if peak <= 0.0:
        return BACKGROUND
    ratio = max(0.0, min(1.0, probability / peak))
    red = int(24 + 205 * ratio)
    green = int(21 + 40 * (1.0 - ratio))
    blue = int(27 + 45 * (1.0 - ratio))
    return f"#{red:02x}{green:02x}{blue:02x}"


class BoardView:
    """Draws a board from a local-truth view dictionary."""

    def __init__(self, parent: tk.Misc, size: int, cell_px: int = 56) -> None:
        self.size = size
        self.cell = cell_px
        pixels = size * cell_px
        self.canvas = tk.Canvas(
            parent, width=pixels, height=pixels, bg=BACKGROUND, highlightthickness=0
        )

    def grid(self, **kwargs) -> None:
        self.canvas.grid(**kwargs)

    def pack(self, **kwargs) -> None:
        self.canvas.pack(**kwargs)

    def render(self, view: dict) -> None:
        """Repaint from a view produced by :func:`p2p_chase.peer.summary.live_view`."""
        self.canvas.delete("all")
        belief = view.get("belief") or [[0.0] * self.size for _ in range(self.size)]
        peak = max((max(row) for row in belief), default=0.0)
        barriers = {tuple(cell) for cell in view.get("barriers", [])}
        scent = view.get("opponent_scent", {})
        position = tuple(view.get("position", (0, 0)))

        for row in range(self.size):
            for col in range(self.size):
                self._cell((row, col), belief[row][col], peak, barriers)
        self._scent_marks(scent)
        self._me(position)

    def _cell(self, cell: Cell, probability: float, peak: float, barriers: set) -> None:
        x0, y0 = cell[1] * self.cell, cell[0] * self.cell
        fill = BARRIER if cell in barriers else belief_colour(probability, peak)
        self.canvas.create_rectangle(
            x0, y0, x0 + self.cell, y0 + self.cell, fill=fill, outline=GRID_LINE
        )
        if cell in barriers:
            self.canvas.create_line(
                x0 + 8, y0 + 8, x0 + self.cell - 8, y0 + self.cell - 8, fill="#0b0d12", width=3
            )
            self.canvas.create_line(
                x0 + self.cell - 8, y0 + 8, x0 + 8, y0 + self.cell - 8, fill="#0b0d12", width=3
            )

    def _scent_marks(self, scent: dict) -> None:
        """Small green pips: the opponent's decaying trail, the unforgeable evidence."""
        for key, value in scent.items():
            try:
                row, col = (int(part) for part in key.split(","))
            except ValueError:
                continue
            if value <= 0.02 or not (0 <= row < self.size and 0 <= col < self.size):
                continue
            radius = 3 + int(6 * min(1.0, value))
            centre_x = col * self.cell + self.cell - 12
            centre_y = row * self.cell + 12
            self.canvas.create_oval(
                centre_x - radius, centre_y - radius, centre_x + radius, centre_y + radius,
                fill=SCENT, outline="",
            )

    def _me(self, position: Cell) -> None:
        x0, y0 = position[1] * self.cell, position[0] * self.cell
        self.canvas.create_oval(
            x0 + 10, y0 + 10, x0 + self.cell - 10, y0 + self.cell - 10,
            fill=SELF_FILL, outline="#eaf3ff", width=2,
        )
        self.canvas.create_text(
            x0 + self.cell / 2, y0 + self.cell / 2, text="ME",
            fill=SELF_TEXT, font=("Segoe UI", 9, "bold"),
        )
