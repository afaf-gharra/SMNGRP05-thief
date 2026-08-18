"""The three league fields, and the settlement digest they must not disturb.

imreeyal shared a completed friendly result (anrbj666-vs-imreeyal) as a diff
target. Both halves matter: the digest proves our settlement scope and
separators match theirs byte for byte, and the fields prove our filing carries
what the course template requires. We shipped without all three, having read
"template-clean" as minimalism.
"""

import hashlib
import json

from p2p_chase.report.artifacts import league_fields
from p2p_chase.report.emit import mutual_signature

SAMPLE_DIGEST = "59147968d71bb917dba60ff9769ec2772eb6e734652cbcd4670e4cc6906bc02c"
GROUPS = ["anrbj666", "imreeyal"]


def _sample_rows():
    spec = [
        (1, "thief", "capture", "anrbj666", 5, 20),
        (2, "police", "capture", "imreeyal", 20, 5),
        (3, "thief", "capture", "anrbj666", 5, 20),
        (4, "police", "survival", "anrbj666", 5, 10),
        (5, "thief", "capture", "anrbj666", 5, 20),
        (6, "police", "survival", "anrbj666", 5, 10),
    ]
    rows = []
    for number, imreeyal_role, result, winner, imreeyal_pts, anrbj_pts in spec:
        other = "police" if imreeyal_role == "thief" else "thief"
        rows.append({
            "sub_game_number": number,
            "roles": {"imreeyal": imreeyal_role, "anrbj666": other},
            "result": result,
            "winner_group": winner,
            "score": {"imreeyal": imreeyal_pts, "anrbj666": anrbj_pts},
        })
    return rows


def test_our_settlement_signature_reproduces_their_published_digest():
    """The scope is the core aggregate WITHOUT tokens, hashed with spaced
    separators. Tokens are per-side and would make the two hashes differ by
    construction."""
    aggregate = {
        "total_score": {"imreeyal": 45, "anrbj666": 85},
        "sub_games_won": {"imreeyal": 1, "anrbj666": 5},
        "ties": 0,
        "winner_group": "anrbj666",
        "series_tie": False,
    }
    assert mutual_signature("anrbj666-vs-imreeyal", aggregate, _sample_rows()) == SAMPLE_DIGEST


def test_compact_separators_would_not_reproduce_it():
    """Guards the one distinction that is easy to lose: commits are sealed with
    compact separators and this signature is not."""
    doc = {
        "game_id": "anrbj666-vs-imreeyal",
        "aggregate": {
            "total_score": {"imreeyal": 45, "anrbj666": 85},
            "sub_games_won": {"imreeyal": 1, "anrbj666": 5},
            "ties": 0, "winner_group": "anrbj666", "series_tie": False,
        },
        "sub_games": _sample_rows(),
    }
    compact = json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert hashlib.sha256(compact.encode()).hexdigest() != SAMPLE_DIGEST


# ------------------------------------------------------------ league fields


def test_a_friendly_never_increments_the_counted_tally():
    fields = league_fields(GROUPS, {"imreeyal": 6, "anrbj666": 1}, "imreeyal",
                           counted=False, first_meeting=True)
    assert fields["games_played_including_this"] == {"imreeyal": 6, "anrbj666": 1}


def test_a_counted_series_includes_itself():
    fields = league_fields(GROUPS, {"imreeyal": 6, "anrbj666": 1}, "imreeyal",
                           counted=True, first_meeting=True)
    assert fields["games_played_including_this"] == {"imreeyal": 7, "anrbj666": 2}


def test_the_diversity_reward_is_derived_and_marks_the_winner():
    """Both teams' filings mark the winner true, whichever side it is. All-false
    out of modesty makes the two filings disagree on a ten-point line."""
    fields = league_fields(GROUPS, {}, "imreeyal", counted=True, first_meeting=True)
    assert fields["diversity_reward_applied"] == {"imreeyal": True, "anrbj666": False}


def test_a_friendly_earns_no_diversity_reward_even_with_a_winner():
    fields = league_fields(GROUPS, {}, "anrbj666", counted=False, first_meeting=True)
    assert fields["diversity_reward_applied"] == {"imreeyal": False, "anrbj666": False}


def test_a_rematch_earns_no_diversity_reward():
    fields = league_fields(GROUPS, {}, "anrbj666", counted=True, first_meeting=False)
    assert fields["diversity_reward_applied"] == {"imreeyal": False, "anrbj666": False}
    assert fields["first_meeting_between_groups"] is False


def test_the_sample_friendly_reproduces_field_for_field():
    """Their published friendly, rebuilt from our own function."""
    fields = league_fields(GROUPS, {"imreeyal": 0, "anrbj666": 0}, "anrbj666",
                           counted=False, first_meeting=True)
    assert fields == {
        "games_played_including_this": {"imreeyal": 0, "anrbj666": 0},
        "first_meeting_between_groups": True,
        "diversity_reward_applied": {"imreeyal": False, "anrbj666": False},
    }
