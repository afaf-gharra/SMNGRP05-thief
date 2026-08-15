"""The end-of-match mutual audit.

Both peers reveal every nonce and every sealed payload; both recompute every
commit the other declared during play. This is the moment the whole trust model
pays off — until now each side has been holding digests it could not read, and
now it can check that the digests were never revised.

A mismatch is not a dispute. SHA-256 is sensitive to a single bit, so a
recomputed hash either matches or it does not, and the book's iron rule applies:
the forging side takes a technical loss and scores zero. There is nothing for a
human to weigh up, which is exactly the point.

The exchange is best-effort by design. The winning peer's process may exit
moments after reading its inbox, killing its server mid-reply, so a failure to
*send* is not treated as a failure to *audit* — we always check whether their
payload already arrived.
"""

import logging

from p2p_chase.constants import Outcome
from p2p_chase.domain.crypto import COMMIT_SCHEME, audit_records
from p2p_chase.domain.protocol import AuditPayload

logger = logging.getLogger(__name__)


def exchange_audit(runtime) -> dict:
    """Reveal our log, verify theirs, and return the verdict."""
    result = runtime.result[0] if runtime.result else Outcome.TIMEOUT.value
    payload = AuditPayload(
        sender=runtime.role.value, records=runtime.records, result_claim=result
    ).to_dict()

    reply = runtime.transport.exchange_audit(payload)
    self_check = audit_records(runtime.records)

    if not reply:
        logger.warning("No audit payload received from the opponent; recording it as absent.")
        return {
            "passed": self_check["passed"],
            "self_check": self_check,
            "opponent": None,
            "opponent_present": False,
            "note": (
                "The opponent did not return an audit payload. Our own chain verifies, "
                "but mutual verification could not be completed."
            ),
        }

    opponent = audit_records(reply.get("records", []))
    agreed_result = reply.get("result_claim")
    verdict = {
        "passed": self_check["passed"] and opponent["passed"],
        "self_check": self_check,
        "opponent": opponent,
        "opponent_present": True,
        "opponent_result_claim": agreed_result,
        "results_agree": agreed_result == result,
        "tampered_by": _blame(self_check, opponent, runtime.role.value),
        # Recorded in our own artifacts only, never sent: the reveal message is a
        # fixed three-key shape and a strict peer raises on anything else.
        "commit_scheme": COMMIT_SCHEME,
    }
    # Every step failing while both sides agree on the outcome is not what forgery
    # looks like -- forgery alters some steps and changes who won. It is what two
    # different digests of the same honest log look like. Say so in the record so
    # the conversation starts from the two constructions rather than an accusation.
    if not opponent["passed"] and opponent["verified_steps"] == 0 and agreed_result == result:
        verdict["likely_scheme_mismatch"] = True
        logger.warning(
            "Every one of the opponent's %d steps failed to verify, yet we agree on "
            "the result. That pattern is a commit-construction disagreement rather "
            "than tampering. Ours is: %s",
            opponent["total_steps"], COMMIT_SCHEME,
        )
    return verdict


def _blame(self_check: dict, opponent: dict, own_role: str) -> str | None:
    """Name who failed, so the report is specific rather than merely negative."""
    mine_bad = not self_check["passed"]
    theirs_bad = not opponent["passed"]
    if mine_bad and theirs_bad:
        return "both"
    if theirs_bad:
        return "opponent"
    if mine_bad:
        return own_role
    return None
