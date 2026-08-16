"""Opponents whose two roles live on two hostnames.

Our peer is one process that alternates roles across six sub-games. Some teams
are built the other way round -- a cop program and a thief program in separate
repositories, each with its own MCP server on its own host. uoh-ay26 publish
exactly that pair.

Against such an opponent a single fixed ``opponent_url`` talks to the right peer
on odd sub-games and to a peer that is not playing on even ones, which is not a
crash but a silent half-series of negotiations sent to the wrong door.
"""

import pytest

from p2p_chase.constants import Role
from p2p_chase.infra.mcp_client import McpTransport
from p2p_chase.peer.orchestrator import Orchestrator, role_for

COP = "https://cop.uohay26game.com/mcp"
THIEF = "https://theif.uohay26game.com/mcp"


@pytest.fixture
def transport() -> McpTransport:
    return McpTransport(COP, inboxes=None, opponent_urls={"cop": COP, "thief": THIEF})


def test_facing_their_thief_dials_their_thief(transport):
    transport.target_role(Role.THIEF.value)
    assert transport.url == THIEF


def test_facing_their_cop_dials_their_cop(transport):
    transport.target_role(Role.THIEF.value)
    transport.target_role(Role.POLICE.value)
    assert transport.url == COP


def test_police_is_spelled_cop_in_the_declaration(transport):
    """Our enum says "police"; the league declaration says "cop"."""
    transport.target_role("police")
    assert transport.url == COP


def test_switching_hosts_drops_the_session():
    """The open session belongs to the old host; reusing it would send our
    opening negotiation down a connection to a peer that is not playing."""
    closed = []
    transport = McpTransport(COP, inboxes=None, opponent_urls={"cop": COP, "thief": THIEF})
    transport.close_session = lambda: closed.append(transport.url)

    transport.target_role(Role.THIEF.value)

    assert closed == [COP]
    assert transport.url == THIEF


def test_staying_on_the_same_host_keeps_the_session():
    closed = []
    transport = McpTransport(COP, inboxes=None, opponent_urls={"cop": COP, "thief": THIEF})
    transport.close_session = lambda: closed.append(transport.url)

    transport.target_role(Role.POLICE.value)

    assert closed == []


def test_an_opponent_with_one_endpoint_is_left_alone():
    """One dual-role process is the common case and must need no configuration."""
    transport = McpTransport(COP, inboxes=None)
    for role in (Role.THIEF.value, Role.POLICE.value):
        transport.target_role(role)
        assert transport.url == COP


def test_a_partial_mapping_falls_back_rather_than_blanking_the_url():
    transport = McpTransport(COP, inboxes=None, opponent_urls={"cop": COP})
    transport.target_role(Role.THIEF.value)
    assert transport.url == COP


# --------------------------------------------------------------- the series


class _Aimed:
    """A transport double that records only what it was aimed at."""

    def __init__(self) -> None:
        self.aimed: list[str] = []

    def target_role(self, opponent_role: str) -> None:
        self.aimed.append(opponent_role)


def test_the_series_alternates_the_endpoint_with_the_roles(config):
    """Six sub-games, natural role thief: we face their cop on the odd ones."""
    transport = _Aimed()
    orchestrator = Orchestrator(config, transport)

    for index in range(1, 7):
        orchestrator._dial_role_for(role_for(Role.THIEF, index))

    assert transport.aimed == ["police", "thief"] * 3


def test_a_transport_without_endpoints_is_not_required_to_have_the_hook(config):
    """The suite plays whole series through in-memory doubles that have no URL."""
    orchestrator = Orchestrator(config, transport=object())
    orchestrator._dial_role_for(Role.THIEF)  # must not raise
