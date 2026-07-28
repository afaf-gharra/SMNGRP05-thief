"""Commit-reveal: the property the whole trust model rests on."""

import pytest

from p2p_chase.domain.crypto import CommitReveal, audit_records, canonical_json, digest
from p2p_chase.exceptions import CryptoError

PAYLOAD = {"step": 3, "move": "MOVE:N", "intent": "lie", "position": [2, 2]}


def test_canonical_json_is_key_order_independent():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})


def test_canonical_json_has_no_incidental_whitespace():
    assert canonical_json({"a": 1, "b": 2}) == '{"a":1,"b":2}'


def test_digest_is_stable_across_key_order():
    assert digest({"x": 1, "y": [2, 3]}) == digest({"y": [2, 3], "x": 1})


def test_seal_then_verify_succeeds():
    sealed = CommitReveal.seal(PAYLOAD)
    CommitReveal.verify(PAYLOAD, sealed["nonce"], sealed["commit"])


def test_every_seal_draws_a_fresh_nonce():
    """Identical payloads must not produce identical commitments, or an opponent
    could recognise a repeated move without ever seeing the reveal."""
    first, second = CommitReveal.seal(PAYLOAD), CommitReveal.seal(PAYLOAD)
    assert first["nonce"] != second["nonce"]
    assert first["commit"] != second["commit"]


def test_a_changed_move_breaks_the_commitment():
    sealed = CommitReveal.seal(PAYLOAD)
    with pytest.raises(CryptoError, match="Commit mismatch"):
        CommitReveal.verify({**PAYLOAD, "move": "MOVE:S"}, sealed["nonce"], sealed["commit"])


def test_a_single_altered_coordinate_breaks_the_commitment():
    sealed = CommitReveal.seal(PAYLOAD)
    with pytest.raises(CryptoError):
        CommitReveal.verify({**PAYLOAD, "position": [2, 3]}, sealed["nonce"], sealed["commit"])


def test_a_wrong_nonce_breaks_the_commitment():
    sealed = CommitReveal.seal(PAYLOAD)
    with pytest.raises(CryptoError):
        CommitReveal.verify(PAYLOAD, "0" * 32, sealed["commit"])


def record(step: int) -> dict:
    payload = {**PAYLOAD, "step": step}
    return {"payload": payload, **CommitReveal.seal(payload)}


def test_a_clean_log_passes_the_audit():
    verdict = audit_records([record(i) for i in range(1, 6)])
    assert verdict["passed"] is True
    assert verdict["verified_steps"] == 5
    assert verdict["failed_steps"] == []


def test_the_audit_names_the_tampered_step():
    records = [record(i) for i in range(1, 6)]
    records[2]["payload"]["move"] = "MOVE:W"          # rewrite history
    verdict = audit_records(records)
    assert verdict["passed"] is False
    assert verdict["failed_steps"] == [3]
    assert verdict["verified_steps"] == 4


def test_the_audit_survives_a_malformed_record():
    verdict = audit_records([{"payload": {"step": 1}}])
    assert verdict["passed"] is False
    assert verdict["failed_steps"] == [1]


def test_an_empty_log_passes_vacuously():
    assert audit_records([])["passed"] is True
