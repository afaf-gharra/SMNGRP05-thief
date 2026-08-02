"""Capture the screenshots the submission requires (book ch.9, Appendix C).

Three images, all produced from a *real* match rather than a mock-up:

* ``live-gui.png``  — the officer's live window mid-match: the belief heatmap,
  the turn banner, and no sight of the opponent.
* ``replay-verified.png`` — the Replay Viewer stamping ``Verified OK`` on the
  untouched log that match produced.
* ``replay-tampered.png`` — the same log with a single coordinate altered,
  proving the auditor actually detects it rather than merely displaying a badge.

    uv run python scripts/capture_screens.py
"""

import copy
import json
import shutil
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from conftest import LoopbackTransport  # noqa: E402
from PIL import ImageGrab  # noqa: E402

from p2p_chase.gui.live_app import LivePeerApp  # noqa: E402
from p2p_chase.gui.replay_app import ReplayApp  # noqa: E402
from p2p_chase.sdk import ChaseSdk  # noqa: E402

IMAGES = ROOT / "docs" / "images"
WORK = ROOT / "_capture"


def prepare(name: str, group_id: str, port_role: str, sub_games: int = 1) -> ChaseSdk:
    directory = WORK / name
    shutil.copytree(ROOT / "config" / port_role, directory)
    shared = json.loads((directory / "game.json").read_text(encoding="utf-8"))
    shared["movement_and_barriers"].update(survival_threshold=30, max_moves=30)
    shared["network_and_league"]["num_games"] = sub_games
    (directory / "game.json").write_text(json.dumps(shared, indent=2), encoding="utf-8")
    sdk = ChaseSdk(directory, workdir=WORK / name)
    sdk.config.override("game.group_id", group_id)
    sdk.config.override("game.group_name", group_id.upper())
    sdk.config.override("network.turn_timeout_seconds", 30)
    return sdk


def grab(widget, path: Path, pad: int = 2) -> None:
    """Grab just this window's rectangle, so the shot is the app and nothing else."""
    widget.update_idletasks()
    widget.update()
    x = widget.winfo_rootx() - pad
    y = widget.winfo_rooty() - pad
    box = (x, y, x + widget.winfo_width() + 2 * pad, y + widget.winfo_height() + 2 * pad)
    IMAGES.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab(bbox=box).save(path)
    print(f"  wrote {path.relative_to(ROOT)}")


class Paced:
    """A transport that paces turns to human speed.

    Over loopback a thirty-step match finishes in well under a second, which is
    fine for a test and useless for a screenshot. This delegates everything and
    simply slows the outbound turn, so the window shows a real match unfolding
    rather than a frozen final frame.
    """

    def __init__(self, inner, delay: float = 0.22) -> None:
        self._inner = inner
        self._delay = delay

    def send_turn(self, message: dict) -> None:
        time.sleep(self._delay)
        self._inner.send_turn(message)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class CapturingApp(LivePeerApp):
    """The live window, grabbing itself once the chase is genuinely under way."""

    grab_at_step = 12
    captured = False

    def _apply(self, event: dict) -> bool:
        finished = super()._apply(event)
        view = event.get("view") or {}
        if not self.captured and view.get("step", 0) >= self.grab_at_step:
            self.captured = True
            grab(self.root, IMAGES / "live-gui.png")
        return finished


def capture_live() -> Path:
    """Play a real match with the officer's window open, grabbing it mid-chase."""
    cop = prepare("cop", "SMNGRP05", "police")
    thief = prepare("thief", "rival-01", "thief")
    left, right = LoopbackTransport.pair()

    threading.Thread(
        target=lambda: thief.play_series("thief", transport=Paced(right), send_email=False),
        daemon=True, name="thief",
    ).start()

    app = CapturingApp(cop, "police", send_email=False, transport=Paced(left))
    app.root.geometry("+80+80")
    app.run()
    if not app.captured:
        raise RuntimeError("the match ended before the live window could be captured")
    return WORK / "cop" / "logs" / "SMNGRP05"


def capture_replay(logs_dir: Path) -> None:
    """Open the auditor on the real log, then on a deliberately corrupted copy."""
    log_path = next(logs_dir.glob("log_*_g01.json"))
    log = json.loads(log_path.read_text(encoding="utf-8"))
    config = ChaseSdk(WORK / "cop").config

    clean = ReplayApp(config, log, log_path=log_path.name)
    clean.root.geometry("+80+80")
    clean.root.after(1200, lambda: grab(clean.root, IMAGES / "replay-verified.png"))
    clean.root.after(2200, clean.root.destroy)
    clean.root.mainloop()

    forged = copy.deepcopy(log)
    victim = next(r for r in forged["records"] if r["payload"].get("step") == 3)
    victim["payload"]["position"] = [6, 6]  # rewrite one coordinate, nothing else
    tampered = ReplayApp(config, forged, log_path="log (one coordinate altered)")
    tampered.root.geometry("+80+80")
    tampered.show_first_failure()  # land on the forged step so the red stamp is on screen
    tampered.root.after(1200, lambda: grab(tampered.root, IMAGES / "replay-tampered.png"))
    tampered.root.after(2200, tampered.root.destroy)
    tampered.root.mainloop()


def main() -> int:
    if WORK.exists():
        shutil.rmtree(WORK)
    print("Playing a match with the live window open...")
    logs_dir = capture_live()
    print("Auditing the log it produced...")
    capture_replay(logs_dir)
    print("Done. Screenshots are in docs/images/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
