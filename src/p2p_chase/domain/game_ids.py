"""Derive the identifiers that tie a match's four report files together.

Both peers must independently arrive at the *same* ``game_id`` and ``game_uid``
without asking anyone, or the lecturer receives two reports that look like two
different matches. So both are computed from data both sides already hold: the
two group codes (sorted, so the order of who dialled whom is irrelevant) and the
signed terms.
"""

from p2p_chase.domain.crypto import digest


def derive_game_ids(
    terms: dict,
    own_group: str,
    peer_group: str,
    agreed_id: str | None = None,
    agreed_uid: str | None = None,
) -> tuple[str, str]:
    """Return ``(game_id, game_uid)`` — a readable name and a collision-proof id.

    ``game_id`` names the fixture and appears in every filename.
    ``game_uid`` additionally binds the agreed terms, so replaying the same two
    teams under different rules produces a distinguishable match.

    Deriving the name from the two group codes is what lets both peers arrive at
    it without asking. It is also too rigid on its own: two teams who warm up
    twice produce the same name twice, the second run overwrites the first
    team's artifacts, and a peer that labels its series separately ends up
    reporting a different fixture from ours. ``agreed_id`` is the escape hatch
    for a label both sides have settled in writing — it must be *agreed*, never
    invented locally, because the whole point of the derivation is that neither
    side gets to name the match unilaterally.

    ``agreed_uid`` is the same escape hatch one level down, and it exists because
    deriving the uid only works when both peers derive it the *same way*. They do
    not. uoh-ay26 report an identical uid for two differently-named series
    against us, so theirs cannot be a function of the match name, while ours is —
    and a uid that cannot tell two series apart cannot do the job the uid exists
    for. Until the league settles one derivation, the reliable way to make two
    reports describe one match is to agree the string itself.
    """
    first, second = sorted([own_group or "unknown", peer_group or "unknown"])
    game_id = agreed_id or f"{first}-vs-{second}"
    if agreed_uid:
        return game_id, agreed_uid
    fingerprint = digest({"game_id": game_id, "terms": terms})
    game_uid = "-".join(
        [fingerprint[0:8], fingerprint[8:12], fingerprint[12:16], fingerprint[16:20],
         fingerprint[20:32]]
    )
    return game_id, game_uid
