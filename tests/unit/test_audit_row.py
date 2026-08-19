"""The rollup's audit block must answer what an opponent reconciles against.

It carried ``log_verified`` alone, so the three questions a peer actually asks of
our result -- was the other side there, did the two claims agree, did anyone
tamper -- were absent from the rollup while the per-sub-game log artifact
carried all three. A reader of the result alone could not distinguish "checked
and false" from "never checked", and a checker expecting a boolean reads a
missing key as null.

An opponent found this before it reached a counted series, which is the whole
argument for playing warm-ups against strangers.
"""

from p2p_chase.report.artifacts import audit_row

CLEAN = {
    "passed": True,
    "opponent_present": True,
    "opponent_result_claim": "survival",
    "results_agree": True,
    "tampered_by": None,
}


def test_a_clean_audit_reports_every_field_a_peer_reconciles_against():
    row = audit_row(CLEAN)
    assert row == {
        "log_verified": True,
        "tampered": False,
        "opponent_present": True,
        "results_agree": True,
        "opponent_result_claim": "survival",
        "tampering_detected": False,
    }


def test_no_field_is_ever_none_where_a_boolean_is_expected():
    """A null is what the league's checker refuses; absence reads as null."""
    for audit in (CLEAN, {}, {"passed": False}):
        row = audit_row(audit)
        for key in ("log_verified", "tampered", "opponent_present", "results_agree",
                    "tampering_detected"):
            assert isinstance(row[key], bool), (key, row[key])


def test_an_empty_audit_claims_nothing_rather_than_claiming_success():
    row = audit_row({})
    assert row["log_verified"] is False
    assert row["opponent_present"] is False
    assert row["results_agree"] is False


def test_a_failed_chain_is_not_an_accusation_of_tampering():
    """Derived, never asserted.

    A chain that fails to verify is a failed chain. Reporting that as tampering
    accuses an opponent of cheating on the evidence of our own bug, and rule 35
    makes a contradicted report expensive for both teams.
    """
    row = audit_row({**CLEAN, "passed": False})
    assert row["log_verified"] is False
    assert row["tampered"] is True
    assert row["tampering_detected"] is False


def test_tampering_is_reported_only_when_a_tamperer_was_named():
    row = audit_row({**CLEAN, "tampered_by": "some-group"})
    assert row["tampering_detected"] is True


def test_the_opponents_own_claim_survives_verbatim():
    """Kept as sent, including None, because it is their word and not our finding."""
    assert audit_row({**CLEAN, "opponent_result_claim": "capture"})[
        "opponent_result_claim"] == "capture"
    assert audit_row({})["opponent_result_claim"] is None
