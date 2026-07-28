"""``Watchdog`` — the last line of defence against a silent freeze (rule 7).

The deadline tracker guards individual waits. The watchdog guards *the process*:
an independent background thread that watches the main loop's heartbeat and, if
it stops, saves the match state and shuts down deliberately.

The distinction matters because the failures it catches are the ones no
in-loop check can see — a model provider that blocks forever inside a C
extension, a deadlocked lock, a GUI thread that stops pumping. In those cases
the main loop is not slow, it is gone, and only something outside it can notice.

Shutting down is not giving up: the state file it writes is what lets the match
be reconstructed and reported rather than silently lost.
"""

import json
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class Watchdog:
    """Background heartbeat monitor with controlled shutdown and state persistence."""

    def __init__(
        self,
        timeout_seconds: float = 300.0,
        state_dir: str | Path = "state",
        poll_seconds: float = 5.0,
        on_freeze: Callable[[], None] | None = None,
        clock=time.monotonic,
    ) -> None:
        self.timeout_seconds = float(timeout_seconds)
        self.state_dir = Path(state_dir)
        self.poll_seconds = float(poll_seconds)
        self._on_freeze = on_freeze
        self._clock = clock
        self._last_beat = clock()
        self._snapshot: Callable[[], dict] | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.triggered = False
        self.beats = 0

    def bind(self, snapshot: Callable[[], dict]) -> None:
        """Register how to capture the state to persist if we have to shut down."""
        self._snapshot = snapshot

    def beat(self) -> None:
        """Called by the main loop each turn: 'still alive'."""
        self._last_beat = self._clock()
        self.beats += 1

    @property
    def silent_for(self) -> float:
        return self._clock() - self._last_beat

    def check(self) -> bool:
        """One liveness test. Returns ``True`` if the loop looks frozen."""
        if self.triggered:
            return True
        if self.silent_for <= self.timeout_seconds:
            return False
        self.triggered = True
        logger.error(
            "Watchdog: no heartbeat for %.1fs (limit %.1fs). Persisting state and stopping.",
            self.silent_for, self.timeout_seconds,
        )
        self.persist()
        if self._on_freeze is not None:
            self._on_freeze()
        return True

    def persist(self) -> Path | None:
        """Write the current state so a frozen match can still be reported."""
        if self._snapshot is None:
            return None
        try:
            payload = self._snapshot()
        except Exception as exc:  # noqa: BLE001 - a failing snapshot must not mask the freeze
            logger.warning("Watchdog snapshot failed: %s", exc)
            return None
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path = self.state_dir / f"watchdog_{int(time.time())}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Watchdog persisted state to %s", path)
        return path

    def start(self) -> None:
        """Run the monitor in a daemon thread so it can never hold the process open."""
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=self.poll_seconds * 2)

    def _run(self) -> None:
        while not self._stop.wait(self.poll_seconds):
            if self.check():
                return

    def summary(self) -> dict:
        return {
            "timeout_seconds": self.timeout_seconds,
            "beats": self.beats,
            "triggered": self.triggered,
            "silent_for_seconds": round(self.silent_for, 2),
        }
