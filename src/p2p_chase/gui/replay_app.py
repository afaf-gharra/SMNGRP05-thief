"""The Replay Viewer — a mandatory submission artifact (rule 20).

The live window answers "what is happening?". This answers the harder question:
"did what was claimed to happen actually happen?" It walks a saved log step by
step, recomputes each SHA-256 commitment from the revealed nonce and payload,
and stamps the result. Green means the past is provably as recorded. Red means
the log was edited after the fact, and the match is void — no appeal, no partial
credit, because the verdict is arithmetic rather than opinion.
"""

import tkinter as tk

from p2p_chase.gui.board_view import BoardView
from p2p_chase.gui.replay_data import TAMPERED, VERIFIED, build_frames, summarise

PANEL_BG = "#0b0d12"
TEXT = "#dfe4ee"
MUTED = "#8b93a7"
OK_GREEN = "#1f7a44"
BAD_RED = "#a91d2c"


class ReplayApp:
    """Steps through a saved log, verifying each record as it renders it."""

    def __init__(self, config, log: dict, log_path: str = "") -> None:
        self.frames = build_frames(log)
        self.header = summarise(log, self.frames)
        self.index = 0

        size = config.require("board.size")
        self.root = tk.Tk()
        self.root.title(f"p2p-chase replay — {log_path or self.header.get('game_id', '')}")
        self.root.configure(bg=PANEL_BG)
        self.board = BoardView(self.root, size, config.get("gui.cell_px", 56))
        self.board.grid(row=0, column=0, padx=12, pady=12)
        self._build_panel()
        self._show()

    def _build_panel(self) -> None:
        panel = tk.Frame(self.root, bg=PANEL_BG)
        panel.grid(row=0, column=1, sticky="n", padx=(0, 14), pady=12)

        self.stamp = tk.Label(
            panel, text=VERIFIED, bg=OK_GREEN, fg="white", width=24,
            font=("Segoe UI", 14, "bold"), pady=12,
        )
        self.stamp.pack(fill="x", pady=(0, 12))

        overall = self.header["status"]
        tk.Label(
            panel,
            text=(
                f"match verdict: {overall}\n"
                f"game     {self.header.get('game_id')}\n"
                f"sub-game {self.header.get('sub_game_number')}\n"
                f"role     {self.header.get('role')}\n"
                f"result   {self.header.get('result')}\n"
                f"steps    {self.header.get('steps')}"
            ),
            bg=PANEL_BG, fg=OK_GREEN if overall == VERIFIED else BAD_RED,
            justify="left", font=("Consolas", 10), anchor="w",
        ).pack(fill="x")

        self.detail = tk.Label(
            panel, text="", bg=PANEL_BG, fg=TEXT, wraplength=280,
            justify="left", font=("Consolas", 10), anchor="w",
        )
        self.detail.pack(fill="x", pady=(12, 0))

        self.said = tk.Label(
            panel, text="", bg=PANEL_BG, fg=MUTED, wraplength=280,
            justify="left", font=("Segoe UI", 10, "italic"), anchor="w",
        )
        self.said.pack(fill="x", pady=(10, 0))

        controls = tk.Frame(panel, bg=PANEL_BG)
        controls.pack(fill="x", pady=(18, 0))
        for label, delta in (("<< prev", -1), ("next >>", 1)):
            tk.Button(
                controls, text=label, command=lambda d=delta: self._step(d),
                bg="#1c2130", fg=TEXT, relief="flat", padx=12, pady=6,
            ).pack(side="left", expand=True, fill="x", padx=2)
        self.root.bind("<Left>", lambda _event: self._step(-1))
        self.root.bind("<Right>", lambda _event: self._step(1))

    def show_first_failure(self) -> int | None:
        """Jump to the first step that fails verification, if there is one.

        A void match is usually one altered byte among hundreds of honest steps,
        so paging through by hand to find it is exactly the manual work this tool
        exists to remove.
        """
        for index, frame in enumerate(self.frames):
            if not frame.verified:
                self.index = index
                self._show()
                return index
        return None

    def _step(self, delta: int) -> None:
        if self.frames:
            self.index = max(0, min(len(self.frames) - 1, self.index + delta))
            self._show()

    def _show(self) -> None:
        if not self.frames:
            self.detail.configure(text="This log contains no replayable steps.")
            return
        frame = self.frames[self.index]
        self.board.render({
            "position": frame.position,
            "barriers": frame.barriers,
            "belief": None,
            "opponent_scent": {},
        })
        verified = frame.verified
        self.stamp.configure(
            text=VERIFIED if verified else TAMPERED, bg=OK_GREEN if verified else BAD_RED
        )
        self.detail.configure(text="\n".join([
            f"step     {frame.step} of {len(self.frames)}",
            f"position {list(frame.position)}",
            f"move     {frame.move}",
            f"intent   {frame.intent}",
            f"sha-256  {'recomputed and matched' if verified else frame.detail}",
        ]))
        self.said.configure(text=f"“{frame.hint}”" if frame.hint else "")

    def run(self) -> None:  # pragma: no cover - Tkinter main loop
        self.root.mainloop()
