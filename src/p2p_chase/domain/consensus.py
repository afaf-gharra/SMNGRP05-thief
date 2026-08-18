"""The end-of-series agreement: one digest both teams must compute identically.

Six sub-games can each audit perfectly and the series still fail, because the
audits prove what happened *inside* a sub-game and nothing at all about whether
the two teams left the table agreeing on the set of six. That gap is not
theoretical: it is what left uoh-ay26's validator reporting
``mutual_agreement.confirmed = false`` on a series where every one of our twelve
audits verified in both directions.

The digest covers the symmetric outcome only — what happened, who held which
role, who won, and for how many points. Everything per-side is excluded on
purpose: timestamps, token counts and commit hashes legitimately differ between
two honest peers, so including any of them would make the two digests differ by
construction and the check could never pass.

The convention below is not read off a specification. uoh-ay26's published spec
and their implementation disagreed in two places, so this was recovered by
rebuilding their live digest from our own signed logs until it matched
``cf8d5dab0bbb5eed012f98dc30cf8bf0ea13c31ca5c53b24f1030739e053b060`` exactly, and
then confirmed with them in writing:

* rows are keyed by the **real group ids**, not a placeholder like "opponent";
* ``game_id`` is the **agreed match id**, not the short series label;
* separators are compact, unlike the settlement signature in :mod:`report.emit`,
  which the league computes with Python's spaced defaults. The two live side by
  side and hash the same facts to different digests, which is exactly why each
  one says so out loud.
"""

import hashlib
import json

#: Exactly the fields both peers can agree on, in the order the spec lists them.
ROW_FIELDS = ("sub_game_number", "result", "roles", "score", "winner_group")


def series_rows(sub_games: list[dict]) -> list[dict]:
    """Trim report rows to the symmetric facts, ordered by sub-game."""
    return [
        {field: row[field] for field in ROW_FIELDS}
        for row in sorted(sub_games, key=lambda item: item["sub_game_number"])
    ]


def series_preimage(game_id: str, game_uid: str, sub_games: list[dict]) -> dict:
    return {
        "game_id": game_id,
        "game_uid": game_uid,
        "sub_games": series_rows(sub_games),
    }


def series_digest(game_id: str, game_uid: str, sub_games: list[dict]) -> str:
    """SHA-256 over the canonical preimage: 64 lowercase hex."""
    canonical = json.dumps(
        series_preimage(game_id, game_uid, sub_games),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_well_formed(digest: str | None) -> bool:
    """A consensus value is 64 lowercase hex characters, or absent."""
    if digest is None:
        return True
    return (
        isinstance(digest, str)
        and len(digest) == 64
        and digest == digest.lower()
        and all(char in "0123456789abcdef" for char in digest)
    )
