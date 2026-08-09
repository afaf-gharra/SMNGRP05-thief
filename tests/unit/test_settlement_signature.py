"""Two hash forms live in this codebase and must never be confused.

Commits are sealed with *compact* canonical JSON; the settlement signature in the
result artifact uses Python's *default spaced* separators, matching the course
reference's report writer and the form the league settled on. Hashing the same
document both ways gives different digests, so a single wrong call here means two
honest teams' reports can never reconcile — and nothing in a match would reveal it.
"""

import hashlib
import json

from p2p_chase.domain.crypto import canonical_json
from p2p_chase.report.emit import mutual_signature

DOCUMENT = {
    "game_id": "SMNGRP05-vs-imreeyal",
    "aggregate": {"total_score": {"SMNGRP05": 45, "imreeyal": 30}},
    "sub_games": [
        {
            "sub_game_number": 1,
            "roles": {"SMNGRP05": "police", "imreeyal": "thief"},
            "result": "capture",
            "winner_group": "SMNGRP05",
            "score": {"SMNGRP05": 20, "imreeyal": 5},
        }
    ],
}


def _signed_document() -> dict:
    return {
        "game_id": DOCUMENT["game_id"],
        "aggregate": DOCUMENT["aggregate"],
        "sub_games": DOCUMENT["sub_games"],
    }


def test_settlement_signature_uses_spaced_separators() -> None:
    expected = hashlib.sha256(
        json.dumps(_signed_document(), sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    actual = mutual_signature(
        DOCUMENT["game_id"], DOCUMENT["aggregate"], DOCUMENT["sub_games"]
    )
    assert actual == expected


def test_settlement_signature_is_not_the_compact_commit_form() -> None:
    """The regression guard: if someone routes this through canonical_json, fail."""
    compact = hashlib.sha256(
        canonical_json(_signed_document()).encode("utf-8")
    ).hexdigest()
    actual = mutual_signature(
        DOCUMENT["game_id"], DOCUMENT["aggregate"], DOCUMENT["sub_games"]
    )
    assert actual != compact


def test_signature_ignores_per_side_fields_in_the_rows() -> None:
    """Timestamps and token counts differ between peers; they must stay out."""
    noisy = [
        {**DOCUMENT["sub_games"][0], "started_at": "2026-08-09T21:30:00", "tokens": {"a": 7}}
    ]
    assert mutual_signature(
        DOCUMENT["game_id"], DOCUMENT["aggregate"], noisy
    ) == mutual_signature(DOCUMENT["game_id"], DOCUMENT["aggregate"], DOCUMENT["sub_games"])


def test_signature_changes_when_a_symmetric_fact_changes() -> None:
    flipped = [{**DOCUMENT["sub_games"][0], "winner_group": "imreeyal"}]
    assert mutual_signature(
        DOCUMENT["game_id"], DOCUMENT["aggregate"], flipped
    ) != mutual_signature(DOCUMENT["game_id"], DOCUMENT["aggregate"], DOCUMENT["sub_games"])
