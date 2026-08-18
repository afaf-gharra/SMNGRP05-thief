"""The reciprocal end-of-series agreement, exchanged after the sixth sub-game.

Twelve clean audits do not add up to an agreed series: they prove what happened
inside each sub-game and say nothing about whether the two teams walked away
holding the same set of six. uoh-ay26's validator reported
``mutual_agreement.confirmed = false`` against a series where every one of our
audits verified in both directions, which is precisely that gap.

The envelope reuses ``submit_audit`` with an empty record list, because it is a
statement *about* the series rather than a disclosure within one; a consensus
envelope carrying game records is malformed by the same convention.

**This is opt-in and must stay opt-in.** Peers built on the course reference
rebuild the payload with ``cls(**data)`` and raise on any key they do not know,
so sending ``consensus_sha`` to one of them ends its process at the audit, after
a complete and otherwise valid match. We have done that to an opponent once
already. It therefore only fires where the config says the opponent implements
it, and the digest is still written to our own report either way.
"""

import logging

from p2p_chase.domain.consensus import is_well_formed
from p2p_chase.domain.protocol import AuditPayload

logger = logging.getLogger(__name__)

#: Result claim naming the envelope for what it is, so a peer reading the
#: records-empty shape has a second, human-legible signal for the same thing.
CLAIM = "series_consensus"


def exchange(transport, role: str, ours: str) -> dict:
    """Send our series digest, collect theirs, and say whether they agree."""
    payload = AuditPayload(
        sender=role, records=[], result_claim=CLAIM, consensus_sha=ours
    ).to_dict()

    reply = transport.exchange_audit(payload)
    if not reply:
        logger.warning("No series-consensus envelope came back from the opponent.")
        return {"ours": ours, "theirs": None, "agreed": False, "note": "no reply"}

    theirs = reply.get("consensus_sha")
    if not is_well_formed(theirs):
        return {
            "ours": ours, "theirs": theirs, "agreed": False,
            "note": "their consensus digest is not 64 lowercase hex",
        }
    if theirs is None:
        return {
            "ours": ours, "theirs": None, "agreed": False,
            "note": "they replied without a consensus digest",
        }
    if reply.get("records"):
        # Not fatal: their outcome claim still stands. Worth recording, because a
        # consensus envelope carrying records means one of us is building it from
        # the wrong thing.
        logger.warning("Their consensus envelope carried %d records.", len(reply["records"]))

    agreed = theirs == ours
    if not agreed:
        logger.warning(
            "Series consensus disagrees: ours %s, theirs %s. The sub-game results "
            "already stand; this says the two filings will not reconcile.",
            ours, theirs,
        )
    return {"ours": ours, "theirs": theirs, "agreed": agreed}
