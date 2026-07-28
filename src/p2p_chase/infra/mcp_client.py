"""``McpTransport`` — the wire, from this peer's point of view.

Outbound calls go to the *opponent's* MCP server; inbound messages arrive in our
own server's inboxes. The whole "network" a peer knows is therefore one URL and
four queues, which is also exactly the surface a test double has to implement —
so the entire game loop can be exercised end-to-end without opening a socket.

Every outbound call retries, because two students starting two terminals seconds
apart is the normal case rather than an error, and every retry is bounded,
because an unbounded one is just a hang with extra steps.
"""

import asyncio
import contextlib
import logging
import queue
import time

from p2p_chase.exceptions import TransportError
from p2p_chase.infra.mcp_server import PeerInboxes

logger = logging.getLogger(__name__)

_ARG_NAME = {"submit_audit": "payload"}  # every other tool takes `message`


class McpTransport:
    """Push to the opponent's tools, pull from our own inboxes."""

    def __init__(
        self, opponent_url: str, inboxes: PeerInboxes, connect_timeout: float = 60.0,
        retry_interval: float = 1.0, audit_timeout: float = 10.0, control_timeout: float = 2.0,
    ) -> None:
        self.url = opponent_url
        self._inboxes = inboxes
        self._connect_timeout = float(connect_timeout)
        self._retry = float(retry_interval)
        self._audit_timeout = float(audit_timeout)
        self._control_timeout = float(control_timeout)

    def _call(self, tool: str, argument: dict) -> None:
        from fastmcp import Client  # noqa: PLC0415

        async def invoke() -> None:
            async with Client(self.url) as client:
                await client.call_tool(tool, {_ARG_NAME.get(tool, "message"): argument})

        asyncio.run(invoke())

    def _call_with_retry(self, tool: str, argument: dict, timeout: float | None = None) -> None:
        deadline = time.monotonic() + (
            self._connect_timeout if timeout is None else timeout
        )
        attempt = 0
        while True:
            attempt += 1
            try:
                self._call(tool, argument)
                return
            except Exception as exc:  # noqa: BLE001 - any transport failure is retryable
                if time.monotonic() >= deadline:
                    raise TransportError(
                        f"Opponent MCP server unreachable at {self.url} after {attempt} "
                        f"attempt(s) calling {tool!r}: {exc}"
                    ) from exc
                time.sleep(self._retry)

    # ------------------------------------------------------------- handshake

    def exchange_agreement(self, signed: dict) -> dict | None:
        self._call_with_retry("negotiate", signed)
        try:
            return self._inboxes.agreements.get(timeout=self._connect_timeout)
        except queue.Empty as exc:
            raise TransportError("The opponent never sent its signed agreement") from exc

    # ------------------------------------------------------------------ play

    def send_turn(self, message: dict) -> None:
        self._call_with_retry("receive_turn", message)

    def poll_turn(self, timeout: float) -> dict | None:
        try:
            return self._inboxes.turns.get(timeout=timeout)
        except queue.Empty:
            return None

    # --------------------------------------------------------------- control

    def send_control(self, message: dict) -> None:
        """Advisory, so a slow or departed opponent must never stall the game."""
        with contextlib.suppress(TransportError):
            self._call_with_retry("receive_control", message, timeout=self._control_timeout)

    def poll_control(self) -> dict | None:
        try:
            return self._inboxes.controls.get_nowait()
        except queue.Empty:
            return None

    # ----------------------------------------------------------------- audit

    def exchange_audit(self, payload: dict) -> dict | None:
        """Reveal our log and collect theirs.

        Sending is best-effort: the winner often exits immediately after reading
        its inbox, which kills its server mid-reply even though our payload
        landed. Their payload may already be sitting in our inbox regardless, so
        we always look.
        """
        with contextlib.suppress(TransportError):
            self._call_with_retry("submit_audit", payload, timeout=self._audit_timeout)
        try:
            return self._inboxes.audits.get(timeout=self._audit_timeout)
        except queue.Empty:
            logger.warning("No audit payload arrived from the opponent within the timeout")
            return None

    def drain_inboxes(self) -> None:
        self._inboxes.drain()
