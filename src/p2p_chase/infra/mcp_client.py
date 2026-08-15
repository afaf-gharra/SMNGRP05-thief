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
        self._loop = None
        self._client = None

    def _call(self, tool: str, argument: dict) -> None:
        """Send one tool call over the session we already hold.

        Opening a fresh MCP session for every call is the obvious implementation
        and it is what we shipped first. It costs four HTTP round trips per turn
        instead of one -- initialise, list tools, call, terminate -- and against a
        real opponent that reached 87 to 124 connections a minute, which is enough
        to make a free tunnel start refusing *new* connections while established
        ones keep working. Their client then failed at sub-game boundaries, where
        it had to open one, and reported us as unreachable while our own logs
        showed no error at all.

        One session per sub-game is all the protocol asks for.
        """
        client = self._session()
        try:
            self._run(
                client.call_tool(tool, {_ARG_NAME.get(tool, "message"): argument})
            )
        except Exception:
            # A broken session is not a broken opponent: drop it so the retry
            # opens a clean one rather than reusing something already dead.
            self.close_session()
            raise

    def _session(self):
        """The open client, opening one if this is the first call of a sub-game."""
        if self._client is None:
            from fastmcp import Client  # noqa: PLC0415

            client = Client(self.url)
            self._run(client.__aenter__())
            self._client = client
        return self._client

    def close_session(self) -> None:
        """End the current MCP session, if any. Safe to call when none is open."""
        client, self._client = self._client, None
        if client is not None:
            with contextlib.suppress(Exception):
                self._run(client.__aexit__(None, None, None))

    def _run(self, coroutine):
        """Drive a coroutine on our own long-lived loop.

        The loop has to outlive the call: ``asyncio.run`` closes the loop it
        creates, which would take the session down with it and defeat the point.
        """
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
        return self._loop.run_until_complete(coroutine)

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
        # A sub-game is its own session on both sides: the opponent tears its
        # server down between them, so carrying ours across the boundary would
        # reuse a connection they have already closed.
        self.close_session()
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
