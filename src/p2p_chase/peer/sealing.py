"""Building the records a peer commits to.

Two kinds of sealed record, both hashed the moment they are created and both
revealed only at the final audit:

* **Step zero** — the hardware declaration, the model in use, the group identity
  and the exact commit hash that is playing. Sealed *before* the first move, so
  it cannot be revised once the result is known (book ch.5; rules 24 and 53).
* **Per step** — the true position, the move, the honesty flag, the hint and the
  reasoning behind it. Note that the *whole* payload is hashed, so the
  prompt/reasoning trail is covered by the audit too: we cannot invent a
  flattering account of our own decisions afterwards.
"""

from datetime import UTC, datetime

from p2p_chase.domain.crypto import CommitReveal
from p2p_chase.domain.own_state import STATIONARY
from p2p_chase.domain.protocol import TurnMessage
from p2p_chase.shared import gitinfo
from p2p_chase.shared.sysinfo import collect_spec
from p2p_chase.shared.terms import describe_scent_model
from p2p_chase.shared.version import CODE_VERSION


def now_iso() -> str:
    """UTC, timezone-aware. Two peers in one room may still disagree on local time."""
    return datetime.now(UTC).isoformat()


def sealed_spec_record(config, sub_game_number: int, repo_root: str | None = None) -> dict:
    """Step zero: who we are, what we run on, which commit is playing."""
    payload = {
        "step": 0,
        "type": "system_spec",
        "spec": collect_spec(),
        "model": config.get("llm.model", "") or "template-zero-token",
        "provider": config.get("trash_talk.provider", "template"),
        "code_version": CODE_VERSION,
        "github_commit": gitinfo.commit_hash(repo_root),
        "git": gitinfo.describe(repo_root),
        "group_id": config.get("game.group_id", "unknown-group"),
        "group_name": config.get("game.group_name", "unnamed"),
        "sub_game_number": sub_game_number,
        "scent_model": describe_scent_model(config),
        "declared_at": now_iso(),
    }
    return {"payload": payload, **CommitReveal.seal(payload)}


def identity_from_config(config) -> dict:
    """Static group identity, exchanged in the handshake.

    Per *group*, not per role: roles alternate across a series, so the thing that
    accumulates a league score is the team, and the declaration must name teams.
    Hardware travels here because only its owner can report it.
    """
    return {
        "group_id": config.get("game.group_id", "unknown-group"),
        "group_name": config.get("game.group_name", "unnamed"),
        "members": config.get("game.members", []),
        "repos": config.get("game.repos", {}),
        "mcp_servers": config.get("game.mcp_servers", {}),
        "llm_model": config.get("llm.model", "") or "template-zero-token",
        # Counted series we have completed, under exactly this key. Opponents
        # read it into their own filing's league fields, and a differently
        # spelled key reads as zero -- understating our count in *their* report,
        # which rule 38 makes our problem as much as theirs.
        "counted_games_played": int(config.get("game.counted_games_played", 0) or 0),
        "git_commit_hash": gitinfo.commit_sha(),
        "spec": collect_spec(),
    }


def board_state_string(state) -> str:
    """A compact, replayable description of the board as this peer sees it."""
    barriers = sorted([list(cell) for cell in state.barriers])
    return (
        f"grid={state.board.size}x{state.board.size};"
        f"self={list(state.position)};barriers={barriers}"
    )


def sealed_step_record(state, decision, usage: dict, tokens_total: int, extra: dict) -> dict:
    """One turn's truth, sealed under a fresh nonce."""
    last = state.log[-1] if state.log else {}
    payload = {
        "step": state.step_number,
        "role": state.role.value,
        "state": board_state_string(state),
        "position": list(state.position),
        # The agreed move_set is the authority on this field: N/S/E/W/STAY and
        # nothing else. The richer internal action name stays in `action`, which
        # no opponent is asked to interpret.
        "move": last.get("wire_move", STATIONARY),
        "action": last.get("move", "-"),
        "barrier_placed": last.get("barrier"),
        "intent": decision.intent,
        "verdict": decision.intent,  # wire-compatible alias for reference peers
        "hint": decision.hint,
        "prompt_discussion": {
            "llm_prompt": decision.prompt_text,
            "llm_reasoning": decision.reasoning,
            "bluff_classification": decision.intent,
            "move_rationale": decision.rationale,
        },
        "model": usage.get("model", "template-zero-token"),
        "tokens_step": usage.get("total", 0),
        "tokens_total": tokens_total,
        "response_seconds": decision.response_seconds,
        **extra,
    }
    return {"payload": payload, **CommitReveal.seal(payload)}


def build_turn_message(
    state, role: str, decision, smell_grid: dict, commit: str,
    capture_claim=None, claim_response=None, win_claim=None,
) -> TurnMessage:
    """Assemble the wire message. The turn token travels with it."""
    barrier = state.last_barrier()
    return TurnMessage(
        step=state.step_number,
        sender=role,
        hint=decision.hint,
        smell_grid=smell_grid,
        commit=commit,
        timestamp=now_iso(),
        barrier_placed=list(barrier) if barrier else None,
        capture_claim=list(capture_claim) if capture_claim else None,
        claim_response=claim_response,
        win_claim=win_claim,
    )
