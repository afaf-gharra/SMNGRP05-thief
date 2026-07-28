"""Condense a finished sub-game into the record everything downstream consumes.

The GUI, the four report artifacts, the replay viewer and the email all read
from this one dictionary, so the runtime is serialised exactly once and every
consumer necessarily agrees with every other.
"""

from p2p_chase.constants import Outcome


def build_summary(runtime) -> dict:
    """Everything worth keeping about one finished sub-game."""
    result, winner = runtime.result or (Outcome.TIMEOUT.value, "-")
    return {
        "sub_game_number": runtime.sub_game_number,
        "role": runtime.role.value,
        "group_id": runtime.own_identity.get("group_id", "unknown-group"),
        "opponent_group_id": runtime.peer_identity.get("group_id", "unknown-opponent"),
        "game_id": runtime.game_id,
        "game_uid": runtime.game_uid,
        "result": result,
        "winner": winner,
        "steps": runtime.state.step_number,
        "unique_cells": runtime.state.unique_cells,
        "barriers_used": runtime.state.my_barriers,
        "barriers_max": runtime.barriers_max,
        "started_at": runtime.started_at,
        "duration_seconds": runtime.duration_seconds,
        "tokens_total": runtime.tokens_total,
        "records": runtime.records,
        "audit": runtime.audit,
        "phase_trail": runtime.phases.path(),
        "deadlines": runtime.deadlines.summary(),
        "watchdog": runtime.watchdog.summary() if runtime.watchdog else None,
        "opponent_profile": runtime.trust.summary(),
        "talker": _talker_summary(runtime),
        "final_position": list(runtime.state.position),
        "move_log": runtime.state.log,
    }


def _talker_summary(runtime) -> dict:
    summary = getattr(runtime.talker, "summary", None)
    return summary() if callable(summary) else {"provider": "unknown"}


def live_view(runtime) -> dict:
    """A snapshot of *local truth only* for the live window (mandatory rules 8-9).

    Note what is absent: the opponent's position. It is absent because we do not
    have it — the belief matrix is the closest thing to it that legitimately
    exists, and rendering anything more would be cheating rather than a display
    choice.
    """
    return {
        "role": runtime.role.value,
        "step": runtime.state.step_number,
        "position": list(runtime.state.position),
        "barriers": sorted(list(cell) for cell in runtime.state.barriers),
        "barriers_used": runtime.state.my_barriers,
        "barriers_max": runtime.barriers_max,
        "belief": runtime.belief.as_matrix(),
        "opponent_scent": runtime.opponent_scent.snapshot(),
        "own_scent": runtime.own_scent.snapshot(),
        "trust": round(runtime.trust.trust, 3),
        "phase": runtime.phases.state.value,
        "steps_remaining": max(
            0, runtime.rules.survival_threshold - runtime.state.step_number
        ),
        "last_hint": runtime.handler.history[-1]["hint"] if runtime.handler.history else "",
    }
