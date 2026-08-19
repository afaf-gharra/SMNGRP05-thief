"""Rule 53 wants the commit that played each sub-game — for BOTH teams.

Our result used to write a placeholder in the opponent's column and point the
reader at their own filing. That is a worse artifact for no reason: the opponent
seals their commit into their step-zero record and hands it to us in the audit
reveal, so by settlement we are already holding the real hash.

Taken from the *revealed* record rather than from the handshake identity on
purpose. The sealed one is fixed before the first move and verified against its
commitment, so it cannot be edited once the result is known.

An opponent found this in a cross-diff of two friendly reports, before it could
reach a counted filing.
"""

from p2p_chase.peer.audit import _declared_commit

THEIRS = "67b824e6ff8111a5b30b354118184d86a800ecfe"
PLACEHOLDER = "declared-in-their-own-report"


def _step(number: int, **payload) -> dict:
    return {"payload": {"step": number, **payload}}


def test_their_commit_comes_out_of_the_step_zero_they_revealed():
    records = [_step(0, github_commit=THEIRS), _step(1, position=[3, 3])]
    assert _declared_commit(records) == THEIRS


def test_a_later_record_cannot_shadow_the_sealed_one():
    """Step zero is the declaration; a hash appearing later is not it."""
    records = [_step(0, github_commit=THEIRS), _step(4, github_commit="0" * 40)]
    assert _declared_commit(records) == THEIRS


def test_an_absent_declaration_is_reported_absent_rather_than_guessed():
    for records in ([], [_step(1, position=[0, 0])], [_step(0)], [_step(0, github_commit="")]):
        assert _declared_commit(records) is None


def test_malformed_records_do_not_take_the_report_down():
    """A peer we do not control produced these; the report must still be filed."""
    assert _declared_commit(["not-a-dict", None, 7]) is None
    assert _declared_commit([{}, {"payload": None}, _step(0, github_commit=THEIRS)]) == THEIRS


def test_the_row_carries_their_real_hash_once_the_audit_reveals_it():
    from p2p_chase.report.emit import _sub_game_row

    summary = {
        "role": "police", "sub_game_number": 1, "result": "survival", "winner": "thief",
        "started_at": "2026-08-19T15:28:30+03:00", "duration_seconds": 60,
        "tokens_total": 0, "records": [_step(0, github_commit="a" * 40)],
        "audit": {"passed": True, "opponent_commit": THEIRS},
    }
    row = _sub_game_row(summary, "g", "SMNGRP05", "imreeyal", {})
    assert row["github_commit"]["imreeyal"] == THEIRS
    assert row["github_commit"]["SMNGRP05"] == "a" * 40


def test_the_placeholder_survives_when_they_never_declared_one():
    from p2p_chase.report.emit import _sub_game_row

    summary = {
        "role": "thief", "sub_game_number": 2, "result": "survival", "winner": "thief",
        "started_at": "2026-08-19T15:28:30+03:00", "duration_seconds": 60,
        "tokens_total": 0, "records": [], "audit": {"passed": True},
    }
    row = _sub_game_row(summary, "g", "SMNGRP05", "imreeyal", {})
    assert row["github_commit"]["imreeyal"] == PLACEHOLDER
