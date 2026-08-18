"""Builders for the four signed JSON artifacts (book ch.9, Appendix F).

Pure functions: each takes facts and returns a dict. No I/O, no clock, no
randomness — which is what lets the test suite assert that two peers holding the
same facts produce the same bytes, the property the whole reporting rule rests
on (mandatory rule 35: contradictory reports void the match for *both* teams).
"""

from p2p_chase.report import schemas
from p2p_chase.report.naming import (
    config_filename,
    ended_at,
    group_block,
    links,
    signature,
)


def build_declaration(
    *, game_id: str, game_uid: str, started_at: str, ended: str, num_sub_games: int,
    token_ceiling: int, own: dict, opponent: dict, timezone: str = schemas.DEFAULT_TIMEZONE,
) -> dict:
    """Artifact 1: the static pre-match declaration for the whole series."""
    groups = sorted(
        [group_block(own), group_block(opponent)], key=lambda block: block["group_id"]
    )
    artifact = {
        "_schema": schemas.DECLARATION,
        "schema_version": schemas.SCHEMA_VERSION,
        "declaration_type": "pre_game_declaration",
        "game_id": game_id,
        "game_uid": game_uid,
        "links": links(game_id),
        "timezone": timezone,
        "game_started_at": started_at,
        "game_ended_at": ended,
        "num_sub_games": num_sub_games,
        "max_tokens_per_game": token_ceiling,
        "groups": {"group_1": groups[0], "group_2": groups[1]},
    }
    artifact["declaration_sha256"] = signature(artifact["groups"])
    return artifact


def build_config(
    *, shared_terms: dict, game_id: str, game_uid: str, sub_game_number: int
) -> dict:
    """Artifact 2: the agreed configuration plus its cryptographic lock.

    The hash covers the *agreed terms only*, not the wrapper, so both peers
    compute the same lock even though each stamps its own filename around it.
    """
    agreed = {key: value for key, value in (shared_terms or {}).items() if not key.startswith("_")}
    return {
        "_schema": schemas.CONFIG,
        **agreed,
        "schema_version": schemas.SCHEMA_VERSION,
        "game_id": game_id,
        "game_uid": game_uid,
        "sub_game_number": sub_game_number,
        "links": links(game_id),
        "config_name": config_filename(game_id, sub_game_number),
        "config_sha256": signature(agreed),
    }


def build_log(*, summary: dict, game_id: str, game_uid: str) -> dict:
    """Artifact 3: one peer's per-sub-game commit-reveal log for the replay auditor."""
    records = summary["records"]
    audit = summary.get("audit") or {}
    return {
        "_schema": schemas.LOG,
        "schema_version": schemas.SCHEMA_VERSION,
        "game_id": game_id,
        "game_uid": game_uid,
        "links": links(game_id),
        "summary": {
            "sub_game_number": summary["sub_game_number"],
            "group_id": summary["group_id"],
            "role": summary["role"],
            "opponent_group_id": summary["opponent_group_id"],
            "result": summary["result"],
            "winner_role": summary["winner"],
            "steps": summary["steps"],
            "timezone": schemas.DEFAULT_TIMEZONE,
            "started_at": summary["started_at"],
            "ended_at": ended_at(summary["started_at"], summary["duration_seconds"]),
            "duration_seconds": summary["duration_seconds"],
            "tokens_total": summary["tokens_total"],
            "barriers_used": summary["barriers_used"],
            "phase_trail": summary["phase_trail"],
            "opponent_profile": summary["opponent_profile"],
            "talker": summary["talker"],
            "audit": audit,
        },
        "records": records,
        "mutual_agreement": {
            "opponent_group_id": summary["opponent_group_id"],
            "sha256": signature(records),
            "confirmed": bool(audit.get("passed")),
        },
    }


def league_fields(
    group_ids: list[str], counts: dict, winner: str | None, *, counted: bool, first_meeting: bool
) -> dict:
    """The three league fields the course template requires in ``final_result``.

    Omitting them is not minimalism, it is an incomplete filing, and each one has
    a trap:

    ``games_played_including_this`` counts **completed counted series only**, so a
    friendly never increments it. The "including this" is true on counted day and
    false every other day.

    ``first_meeting_between_groups`` is about counted history with this opponent,
    not about whether we have ever spoken.

    ``diversity_reward_applied`` is **derived, never claimed**: counted AND first
    meeting AND this group won. Both teams' filings therefore mark the *winner*
    true, whichever side that is. Marking it all-false out of modesty makes the
    two filings visibly disagree on a ten-point line, which is exactly the
    contradiction rule 35 scores as nobody winning.
    """
    played = {group: int(counts.get(group, 0)) + (1 if counted else 0) for group in group_ids}
    return {
        "games_played_including_this": played,
        "first_meeting_between_groups": bool(first_meeting),
        "diversity_reward_applied": {
            group: bool(counted and first_meeting and winner == group) for group in group_ids
        },
    }


def build_result(
    *, game_id: str, game_uid: str, group_ids: list[str], sub_games: list[dict],
    aggregate: dict, mutual_sha256: str, token_totals: dict, league: dict | None = None,
) -> dict:
    """Artifact 4: the aggregated final result both teams must agree on."""
    return {
        "_schema": schemas.RESULT,
        "schema_version": schemas.SCHEMA_VERSION,
        "report_type": "final_game_result",
        "game_id": game_id,
        "game_uid": game_uid,
        "links": links(game_id),
        "timezone": schemas.DEFAULT_TIMEZONE,
        "groups": sorted(group_ids),
        "num_sub_games": len(sub_games),
        "sub_games": sub_games,
        "final_result": {
            **aggregate,
            "tokens_total_series": token_totals,
            **(league or {}),
        },
        "mutual_agreement": {
            "sha256": mutual_sha256,
            "confirmed": all(
                game.get("audit", {}).get("log_verified", False) for game in sub_games
            ),
        },
    }
