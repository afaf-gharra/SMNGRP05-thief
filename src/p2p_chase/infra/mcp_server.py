"""This peer's own FastMCP server — its public mailbox on the internet.

There is no central server, ever. Each agent runs one of these and exposes four
tools; the opponent, acting as a client, pushes messages into them. Inbound
messages land in thread-safe queues that the runtime drains on its own schedule,
which keeps the network thread and the game loop entirely decoupled.

Binding to ``0.0.0.0`` is deliberate: for league play the port is published
through an ngrok/Localtonet tunnel, and a server bound to loopback is invisible
to it (book ch.2, mandatory rule 10).
"""

import logging
import queue
import socket
import threading

from p2p_chase.exceptions import TransportError

logger = logging.getLogger(__name__)


class PeerInboxes:
    """Thread-safe mailboxes: filled by MCP tools, drained by the runtime."""

    def __init__(self) -> None:
        self.agreements: queue.Queue = queue.Queue()
        self.turns: queue.Queue = queue.Queue()
        self.audits: queue.Queue = queue.Queue()
        self.controls: queue.Queue = queue.Queue()

    def drain(self) -> None:
        """Discard stale messages so a restarted series begins from a clean slate."""
        for inbox in (self.turns, self.audits, self.controls):
            while True:
                try:
                    inbox.get_nowait()
                except queue.Empty:
                    break


def ensure_port_free(host: str, port: int) -> None:
    """Fail early and legibly if our port is taken, rather than half-starting."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except OSError as exc:
        raise TransportError(
            f"Port {port} on {host} is already in use — a previous peer is probably still "
            f"running.\n  PowerShell: Get-NetTCPConnection -LocalPort {port} -State Listen | "
            f"Select-Object OwningProcess\n  then: Stop-Process -Id <PID>\n"
            f"Alternatively change network.my_port in this peer's config/<role>/game.toml."
        ) from exc
    finally:
        probe.close()


def build_server(role: str, inboxes: PeerInboxes):
    """A FastMCP app exposing this peer's four receive tools."""
    from fastmcp import FastMCP  # noqa: PLC0415 - keeps import cost off the unit tests

    mcp = FastMCP(name=f"p2p-chase-{role}")

    @mcp.tool
    def negotiate(message: dict) -> dict:
        """Receive the opponent's signed game agreement."""
        inboxes.agreements.put(message)
        return {"ok": True}

    @mcp.tool
    def receive_turn(message: dict) -> dict:
        """Receive the opponent's turn — this also passes the turn token to me."""
        inboxes.turns.put(message)
        return {"ok": True}

    @mcp.tool
    def submit_audit(payload: dict) -> dict:
        """Receive the opponent's end-of-match reveal (records and nonces)."""
        inboxes.audits.put(payload)
        return {"ok": True}

    @mcp.tool
    def receive_control(message: dict) -> dict:
        """Receive an out-of-band control signal (enable / status / restart / quit)."""
        inboxes.controls.put(message)
        return {"ok": True}

    return mcp


def start_server(role: str, host: str, port: int) -> PeerInboxes:
    """Start this peer's MCP server on a daemon thread and return its inboxes."""
    ensure_port_free(host, port)
    inboxes = PeerInboxes()
    server = build_server(role, inboxes)
    thread = threading.Thread(
        target=lambda: server.run(
            transport="http", host=host, port=port, show_banner=False, log_level="warning"
        ),
        daemon=True,
        name=f"mcp-{role}",
    )
    thread.start()
    logger.info("MCP server for %s listening on %s:%s", role, host, port)
    return inboxes
