"""The live window: local truth, a belief heatmap and a turn banner.

Two things make this more than decoration. The **heatmap** turns an abstract
probability matrix into something a person can read at a glance, which is how
you notice that your filter has locked onto the wrong corner. The **turn
banner** is the asynchronous state machine made visible: green when the token is
ours, grey once the commitment is sent and the interface is locked.

The window shows what this agent knows and nothing else. There is no
bird's-eye view, because there is no bird — the opponent's position genuinely
does not exist in this process.
"""

import queue
import threading
import tkinter as tk

from p2p_chase.gui.board_view import BoardView

PANEL_BG = "#0b0d12"
TEXT = "#dfe4ee"
MUTED = "#8b93a7"
GREEN = "#2e9e5b"
GREY = "#404859"


class LivePeerApp:
    """Runs a series on a worker thread and mirrors it in a Tkinter window."""

    def __init__(self, sdk, role: str, send_email: bool = True, transport=None) -> None:
        self.sdk = sdk
        self.role = role
        self.send_email = send_email
        self.transport = transport  # injectable so the window can be exercised offline
        self.events: queue.Queue = queue.Queue()
        self.outcome: dict | None = None
        self.error: BaseException | None = None
        self._runtime = None

        size = sdk.config.require("board.size")
        self.root = tk.Tk()
        self.root.title(f"p2p-chase — {sdk.config.get('game.group_name', 'peer')} ({role})")
        self.root.configure(bg=PANEL_BG)
        self.board = BoardView(self.root, size, sdk.config.get("gui.cell_px", 56))
        self.board.grid(row=0, column=0, padx=12, pady=12)
        self._build_panel()

    def _build_panel(self) -> None:
        panel = tk.Frame(self.root, bg=PANEL_BG)
        panel.grid(row=0, column=1, sticky="n", padx=(0, 14), pady=12)

        self.banner = tk.Label(
            panel, text="WAITING", bg=GREY, fg="white", width=22,
            font=("Segoe UI", 13, "bold"), pady=10,
        )
        self.banner.pack(fill="x", pady=(0, 12))

        self.stats = tk.Label(
            panel, text="", bg=PANEL_BG, fg=TEXT, justify="left",
            font=("Consolas", 10), anchor="w",
        )
        self.stats.pack(fill="x")

        tk.Label(
            panel, text="what they said", bg=PANEL_BG, fg=MUTED,
            font=("Segoe UI", 9, "bold"), anchor="w",
        ).pack(fill="x", pady=(14, 2))
        self.hint = tk.Label(
            panel, text="—", bg=PANEL_BG, fg=TEXT, wraplength=260,
            justify="left", font=("Segoe UI", 10, "italic"), anchor="w",
        )
        self.hint.pack(fill="x")

        tk.Label(
            panel, text="local truth only — the opponent's position is not shown\n"
                        "because this process does not have it",
            bg=PANEL_BG, fg=MUTED, wraplength=260, justify="left", font=("Segoe UI", 8),
        ).pack(fill="x", pady=(16, 0))

    # ------------------------------------------------------------------- run

    def run(self) -> dict:
        worker = threading.Thread(target=self._play, daemon=True, name="series")
        worker.start()
        self.root.after(120, self._pump)
        self.root.mainloop()
        if self.error is not None:
            raise self.error
        return self.outcome or {}

    def _play(self) -> None:
        try:
            self.outcome = self.sdk.play_series(
                self.role, transport=self.transport, listener=self.events.put,
                send_email=self.send_email,
            )
        except BaseException as exc:  # noqa: BLE001 - re-raised on the main thread
            self.error = exc
        finally:
            self.events.put({"type": "finished"})

    def _pump(self) -> None:
        """Drain events on the UI thread; Tkinter is not thread-safe."""
        finished = False
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            finished = self._apply(event) or finished
        if finished:
            self.root.after(900, self.root.destroy)
            return
        self.root.after(120, self._pump)

    def _apply(self, event: dict) -> bool:
        kind = event.get("type")
        if kind == "finished":
            self.banner.configure(text="MATCH OVER", bg=GREY)
            return True
        if kind == "view":
            self._render(event["view"])
        elif kind == "incoming":
            self.banner.configure(text="YOUR TURN", bg=GREEN)
            self.hint.configure(text=f"“{event.get('message', {}).get('hint', '')}”")
        elif kind == "moved":
            self.banner.configure(text="LOCKED — committed", bg=GREY)
        elif kind == "sub_game_start":
            self.banner.configure(
                text=f"SUB-GAME {event['sub_game_number']} ({event['role']})", bg=GREY
            )
        return False

    def _render(self, view: dict) -> None:
        self.board.render(view)
        self.stats.configure(text="\n".join([
            f"phase      {view.get('phase', '-')}",
            f"step       {view.get('step', 0)}",
            f"remaining  {view.get('steps_remaining', 0)}",
            f"walls      {view.get('barriers_used', 0)}/{view.get('barriers_max', 0)}",
            f"trust      {view.get('trust', 0.5):.2f}",
        ]))
