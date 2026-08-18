"""The end-of-series agreement, and the guard that keeps it off strict peers.

Twelve verified audits do not prove the two teams left the table holding the
same set of six sub-games. uoh-ay26's validator reported
``mutual_agreement.confirmed = false`` against a series where every one of our
audits verified both ways, which is exactly that gap.

The convention here was recovered, not read: their published spec and their
implementation disagreed in two places, so it was rebuilt from our own signed
logs until it reproduced their live digest, then confirmed in writing.
"""

import json

import pytest

from p2p_chase.domain.consensus import is_well_formed, series_digest, series_rows
from p2p_chase.domain.protocol import AuditPayload
from p2p_chase.peer.consensus_exchange import CLAIM, exchange

#: Our real W011 series against uoh-ay26, and the digest both sides hold.
W011_GAME_ID = "SMNGRP05-vs-uoh-ay26-W011"
W011_GAME_UID = "63376864-62cf-5bce-54a5-86e9fdc3735b"
W011_DIGEST = "1579909f3ba4db4fd43c455062154c6d053a048f706326f36b315e6e012abf41"


def _w011_rows() -> list[dict]:
    rows = []
    for number in range(1, 7):
        we_are_thief = number % 2 == 1
        roles = {
            "SMNGRP05": "thief" if we_are_thief else "police",
            "uoh-ay26": "police" if we_are_thief else "thief",
        }
        score = {
            "SMNGRP05": 10 if we_are_thief else 5,
            "uoh-ay26": 5 if we_are_thief else 10,
        }
        rows.append({
            "sub_game_number": number,
            "result": "survival",
            "roles": roles,
            "score": score,
            "winner_group": "SMNGRP05" if we_are_thief else "uoh-ay26",
            # Per-side noise that must not reach the digest.
            "started_at": "2026-08-17T19:45:08+00:00",
            "github_commit": {"SMNGRP05": "deadbeef"},
            "tokens": {"SMNGRP05": 0},
        })
    return rows


def test_the_digest_reproduces_the_one_the_opponent_computed():
    """The regression that pins the whole convention."""
    assert series_digest(W011_GAME_ID, W011_GAME_UID, _w011_rows()) == W011_DIGEST


def test_per_side_facts_are_excluded():
    """Timestamps, tokens and commits differ between two honest peers, so a
    digest that included them could never match by construction."""
    assert {key for row in series_rows(_w011_rows()) for key in row} == {
        "sub_game_number", "result", "roles", "score", "winner_group",
    }


def test_the_digest_does_not_depend_on_row_order():
    shuffled = list(reversed(_w011_rows()))
    assert series_digest(W011_GAME_ID, W011_GAME_UID, shuffled) == W011_DIGEST


def test_the_uid_is_inside_the_digest():
    """Two series that differ only by uid must not share a consensus value —
    this is what made the W010 filings disagree."""
    other = series_digest(W011_GAME_ID, "6d78d603-8930-4738-a68f-d5f79eec5ee1", _w011_rows())
    assert other != W011_DIGEST


@pytest.mark.parametrize("value,ok", [
    (None, True),
    ("a" * 64, True),
    ("A" * 64, False),
    ("a" * 63, False),
    ("z" * 64, False),
    (123, False),
])
def test_a_consensus_value_is_64_lowercase_hex_or_absent(value, ok):
    assert is_well_formed(value) is ok


# ------------------------------------------------------- the wire shape


def test_an_ordinary_audit_still_carries_exactly_three_keys():
    """The reference rebuilds this with ``cls(**data)`` and raises on extras, so
    a null ``consensus_sha`` would kill it just as surely as a populated one."""
    sent = AuditPayload("thief", [], "survival").to_dict()
    assert set(sent) == {"sender", "records", "result_claim"}
    AuditPayload(**sent)  # must not raise


def test_the_envelope_carries_the_digest_and_no_records():
    sent = AuditPayload("thief", [], CLAIM, consensus_sha="a" * 64).to_dict()
    assert sent["consensus_sha"] == "a" * 64
    assert sent["records"] == []
    assert json.dumps(sent)  # serialisable as-is


class _Peer:
    def __init__(self, reply):
        self.reply = reply
        self.sent = None

    def exchange_audit(self, payload):
        self.sent = payload
        return self.reply


def test_matching_digests_agree():
    peer = _Peer({"sender": "police", "records": [], "consensus_sha": W011_DIGEST})
    verdict = exchange(peer, "thief", W011_DIGEST)
    assert verdict["agreed"] is True
    assert peer.sent["result_claim"] == CLAIM
    assert peer.sent["records"] == []


def test_differing_digests_do_not_agree():
    peer = _Peer({"sender": "police", "records": [], "consensus_sha": "b" * 64})
    assert exchange(peer, "thief", W011_DIGEST)["agreed"] is False


def test_a_silent_peer_is_recorded_rather_than_assumed_to_agree():
    verdict = exchange(_Peer(None), "thief", W011_DIGEST)
    assert verdict["agreed"] is False
    assert verdict["theirs"] is None


def test_a_peer_that_omits_the_digest_does_not_agree():
    peer = _Peer({"sender": "police", "records": []})
    verdict = exchange(peer, "thief", W011_DIGEST)
    assert verdict["agreed"] is False


def test_a_malformed_digest_does_not_agree():
    peer = _Peer({"sender": "police", "records": [], "consensus_sha": "NOTHEX"})
    assert exchange(peer, "thief", W011_DIGEST)["agreed"] is False
