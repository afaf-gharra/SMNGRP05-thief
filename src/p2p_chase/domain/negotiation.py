"""Pre-game handshake: agree the constitution, sign it, verify the other signature.

Both peers must be playing the *same game*. With no server to hand down the
rules, the agreed terms are hashed and exchanged: each side signs
``SHA-256(canonical_terms || nonce)`` and checks that the opponent signed the
identical dictionary. A single differing value — a bigger board, a slower decay,
one extra barrier — aborts before the first move rather than producing two
irreconcilable realities halfway through (mandatory rule 11).

Group identity travels alongside the terms but is deliberately **not** covered by
the signature: identity legitimately differs between the two peers, so demanding
a match on it would make every honest handshake fail.
"""

import secrets

from p2p_chase.domain.crypto import CommitReveal
from p2p_chase.exceptions import AgreementError, CryptoError


class Negotiation:
    """One peer's side of the agreement exchange."""

    def __init__(self, terms: dict, identity: dict | None = None) -> None:
        self.terms = terms
        self.identity = identity or {}
        self._nonce = secrets.token_hex(16)
        self.peer_identity: dict = {}

    def signed(self) -> dict:
        """My agreement message: the terms, my nonce, my signature, my identity."""
        return {
            "terms": self.terms,
            "nonce": self._nonce,
            "signature": CommitReveal.commit_of(self.terms, self._nonce),
            "identity": self.identity,
        }

    def verify_peer(self, message: dict) -> None:
        """Check the opponent signed exactly the terms I hold; raise otherwise."""
        try:
            their_terms = message["terms"]
            their_nonce = message["nonce"]
            their_signature = message["signature"]
        except (KeyError, TypeError) as exc:
            raise AgreementError(f"Malformed agreement message: {message!r}") from exc

        if their_terms != self.terms:
            raise AgreementError(
                "Agreed terms differ, so no fair match is possible. "
                f"Mismatched keys: {sorted(diff_terms(self.terms, their_terms))}"
            )
        try:
            CommitReveal.verify(their_terms, their_nonce, their_signature)
        except CryptoError as exc:
            raise AgreementError(f"Opponent's signature does not verify: {exc}") from exc
        self.peer_identity = message.get("identity", {}) or {}


def diff_terms(mine: dict, theirs: dict) -> list[str]:
    """Which agreed keys disagree — so the error message is actionable, not just 'no'."""
    keys = set(mine) | set(theirs or {})
    return sorted(key for key in keys if mine.get(key) != (theirs or {}).get(key))
