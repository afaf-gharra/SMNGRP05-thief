"""Write a whole series' four artifacts to disk and return the result.

One declaration and one result per match, plus a config and a log per sub-game.
Everything is filed under this peer's own ``group_id`` subfolder so that two
peers sharing one machine during development do not overwrite each other's
reports — roles alternate, so the group code is the only stable discriminator.

The key subtlety is the *mutual signature*. Both teams must produce the same
hash or the lecturer sees two contradicting reports and voids the match, so the
signature deliberately covers only the symmetric facts — roles, outcomes, scores
and the aggregate. Wall-clock timestamps and per-peer token counts legitimately
differ between the two machines and are therefore excluded.
"""

import hashlib
import json
from pathlib import Path

from p2p_chase.domain import scoring
from p2p_chase.domain.consensus import series_digest
from p2p_chase.report.artifacts import (
    audit_row,
    build_config,
    build_declaration,
    build_log,
    build_result,
    league_fields,
)
from p2p_chase.report.naming import (
    config_filename,
    declaration_filename,
    ended_at,
    log_filename,
    result_filename,
)

DEFAULT_TOKEN_CEILING = 200_000


def write_json(directory: Path, filename: str, data: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def emit_series(config, logs_dir: str | Path, series) -> dict:
    """Write all four artifacts and return the result dict (the emailed payload)."""
    own = series.own_identity
    opponent = series.peer_identity or {"group_id": "unknown-opponent"}
    own_id = own.get("group_id", "unknown-group")
    opponent_id = opponent.get("group_id", "unknown-opponent")
    game_id = series.game_id or f"{own_id}-vs-{opponent_id}"
    game_uid = series.game_uid or "0"
    summaries = series.summaries
    table = config.get("scoring") or scoring.DEFAULT_SCORING
    out_dir = Path(logs_dir) / own_id

    first, last = summaries[0], summaries[-1]
    write_json(out_dir, declaration_filename(game_id), build_declaration(
        game_id=game_id, game_uid=game_uid,
        started_at=first["started_at"],
        ended=ended_at(last["started_at"], last["duration_seconds"]),
        num_sub_games=len(summaries),
        token_ceiling=config.get("league.token_budget", DEFAULT_TOKEN_CEILING),
        own=own, opponent=opponent,
    ))

    sub_games = []
    for summary in summaries:
        number = summary["sub_game_number"]
        write_json(out_dir, config_filename(game_id, number), build_config(
            shared_terms=config.shared, game_id=game_id, game_uid=game_uid,
            sub_game_number=number,
        ))
        write_json(out_dir, log_filename(game_id, number), build_log(
            summary=summary, game_id=game_id, game_uid=game_uid,
        ))
        sub_games.append(_sub_game_row(summary, game_id, own_id, opponent_id, table))

    aggregate = scoring.aggregate(
        [row["score"] for row in sub_games], table.get("tie_score", 2)
    )
    result = build_result(
        game_id=game_id, game_uid=game_uid, group_ids=[own_id, opponent_id],
        sub_games=sub_games, aggregate=aggregate,
        mutual_sha256=mutual_signature(game_id, aggregate, sub_games),
        token_totals=_token_totals(sub_games, [own_id, opponent_id]),
        league=league_fields(
            sorted([own_id, opponent_id]),
            {
                own_id: config.get("game.counted_games_played", 0) or 0,
                opponent_id: opponent.get("counted_games_played", 0) or 0,
            },
            aggregate.get("winner_group"),
            counted=bool(config.get("league.counted", False)),
            first_meeting=bool(config.get("league.first_meeting", True)),
        ),
    )
    # The end-of-series agreement, alongside (not instead of) the settlement
    # signature above. They cover the same facts with different separators and
    # different scope, so both are recorded and neither is derived from the
    # other; see domain.consensus for why the convention is what it is.
    result["mutual_agreement"]["series_consensus_sha"] = series_digest(
        game_id, game_uid, sub_games
    )
    write_json(out_dir, result_filename(game_id), result)
    return result


def _sub_game_row(summary: dict, game_id: str, own_id: str, opponent_id: str, table: dict) -> dict:
    """One sub-game's row in the result: who played what, and what it was worth."""
    own_role = summary["role"]
    roles = {own_id: own_role, opponent_id: "thief" if own_role == "police" else "police"}
    number = summary["sub_game_number"]
    score = scoring.score_subgame(summary["result"], roles, table)
    winner = next((group for group, role in roles.items() if role == summary["winner"]), None)
    commit = _own_commit(summary)
    audit = summary.get("audit") or {}
    return {
        "sub_game_number": number,
        "roles": roles,
        "started_at": summary["started_at"],
        "ended_at": ended_at(summary["started_at"], summary["duration_seconds"]),
        "result": summary["result"],
        "winner_group": winner,
        "tie": winner is None,
        # Their real hash, not a pointer to their filing. They seal it into step
        # zero and reveal it in the audit, so by settlement we hold it -- and a
        # sealed hash cannot be edited once the result is known, which a hash
        # copied from the handshake could. Falls back to the placeholder only
        # when they sealed no step zero: absent is reported, never invented.
        "github_commit": {
            own_id: commit,
            opponent_id: audit.get("opponent_commit") or "declared-in-their-own-report",
        },
        # Zero, not null, for the opponent. Their spend is theirs to report and we
        # cannot know it, but the field is a *numeric map* and a null makes it
        # unsummable -- the league's artifact checker refuses the whole filing on
        # it. Both sides therefore declare own-spend-plus-zero, and the token
        # columns legitimately differ between the two reports while everything
        # else in final_result must not.
        "tokens": {own_id: summary["tokens_total"], opponent_id: 0},
        "score": score,
        "log_files": {
            own_id: f"{own_id}/{log_filename(game_id, number)}",
            opponent_id: f"{opponent_id}/{log_filename(game_id, number)}",
        },
        "audit": audit_row(audit),
    }


def _own_commit(summary: dict) -> str:
    """The commit hash sealed into this sub-game's step-zero record (rule 53)."""
    for record in summary.get("records", []):
        payload = record.get("payload", {})
        if payload.get("step") == 0:
            return payload.get("github_commit", "unknown")
    return "unknown"


def _token_totals(sub_games: list[dict], group_ids: list[str]) -> dict:
    return {
        group: sum(row["tokens"].get(group) or 0 for row in sub_games) for group in group_ids
    }


def mutual_signature(game_id: str, aggregate: dict, sub_games: list[dict]) -> str:
    """Hash only the facts both peers must agree on, so both compute it identically.

    Deliberately **not** :func:`p2p_chase.domain.crypto.canonical_json`. Commits
    are sealed with compact separators; this settlement signature uses Python's
    default *spaced* ones, which is the form the course reference's own report
    writer emits and the form the league has settled on. The two forms hash the
    same document to different digests, so the distinction is load-bearing: get
    it wrong and two honest teams' reports can never agree, no matter how
    perfectly the match itself was played.

    The scope is the symmetric outcome only. Anything per-side — timestamps,
    token counts, commit hashes — would make the two hashes differ by
    construction, which is precisely what this signature exists to disprove.
    """
    return _settlement_digest({
        "game_id": game_id,
        "aggregate": aggregate,
        "sub_games": [
            {
                "sub_game_number": row["sub_game_number"],
                "roles": row["roles"],
                "result": row["result"],
                "winner_group": row["winner_group"],
                "score": row["score"],
            }
            for row in sub_games
        ],
    })


def _settlement_digest(document: dict) -> str:
    """SHA-256 over the settlement form: sorted keys, spaced separators, UTF-8."""
    blob = json.dumps(document, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def consensus_digest_for(config, series) -> str:
    """The series digest, computed without writing a single artifact.

    Ordering is the whole point. We used to send the consensus envelope after
    ``emit_series`` had written fourteen files, and uoh-ay26 run one process per
    sub-game: by the time our envelope left, the peer that should have received
    it had exited. Their digest matched ours exactly and their filing still said
    confirmed=false, because agreement they never received is not agreement.
    """
    own = series.own_identity
    opponent = series.peer_identity or {"group_id": "unknown-opponent"}
    own_id = own.get("group_id", "unknown-group")
    opponent_id = opponent.get("group_id", "unknown-opponent")
    game_id = series.game_id or f"{own_id}-vs-{opponent_id}"
    table = config.get("scoring") or scoring.DEFAULT_SCORING
    rows = [
        _sub_game_row(summary, game_id, own_id, opponent_id, table)
        for summary in series.summaries
    ]
    return series_digest(game_id, series.game_uid or "0", rows)
