"""The pre-game handshake.

Exchange signed terms and group identity, verify the opponent signed the same
constitution we hold, and derive the shared identifiers the four report files
will be filed under. Only then does the match clock start.

Kept separate from the runtime because it is the one part of a sub-game that is
allowed to *refuse*: a terms mismatch is not a bad turn, it is a reason there
should be no turns at all.
"""

import time

from p2p_chase.domain.game_ids import derive_game_ids
from p2p_chase.domain.negotiation import Negotiation
from p2p_chase.exceptions import AgreementError
from p2p_chase.shared.terms import terms_from_config, validate_agreement


def negotiate(runtime) -> dict:
    """Run the agreement exchange for one sub-game; returns the agreed terms."""
    validate_agreement(runtime.config)
    terms = terms_from_config(runtime.config)
    negotiation = Negotiation(terms, identity=runtime.own_identity)

    reply = runtime.transport.exchange_agreement(negotiation.signed())
    if reply is None:
        raise AgreementError("The opponent never sent its signed agreement")
    negotiation.verify_peer(reply)

    runtime.peer_identity = negotiation.peer_identity
    runtime.game_id, runtime.game_uid = derive_game_ids(
        terms,
        runtime.own_identity.get("group_id", "unknown-group"),
        runtime.peer_identity.get("group_id", "unknown-opponent"),
        # Only ever a label both peers have agreed in writing. Left unset, the
        # name is derived from the two group codes as before.
        runtime.config.get("game.series_id") or None,
    )
    runtime._started = time.monotonic()  # the clock starts at agreement, not at import
    return terms
