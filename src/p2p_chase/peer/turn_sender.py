"""Assembling and transmitting one outbound turn.

The order here is load-bearing. The move is applied to local truth *first*, then
sealed, then the scent is deposited, and only then does anything leave the
machine. That sequence guarantees the commitment covers the state we actually
reached — sealing a move we then fail to apply would produce a log that fails
our own audit.
"""

from p2p_chase.constants import FINAL_CAUGHT_HINT, Intent, MoveType, Outcome, Role
from p2p_chase.peer.sealing import build_turn_message, sealed_step_record
from p2p_chase.strategy.base import Decision, TurnContext


def build_context(runtime) -> TurnContext:
    """Everything the brain is allowed to see this turn."""
    history = runtime.handler.history
    return TurnContext(
        state=runtime.state,
        belief=runtime.belief,
        trust=runtime.trust,
        opponent_hint=history[-1]["hint"] if history else "",
        setting=runtime.config.get("play.setting", "") or "",
        barriers_max=runtime.barriers_max,
        steps_remaining=max(0, runtime.rules.survival_threshold - runtime.state.step_number),
        deadline_seconds=runtime.config.get("llm.step_deadline_seconds"),
    )


def take_turn(runtime, claim_response: dict | None) -> None:
    """Decide, apply, seal and send one turn."""
    state = runtime.state

    # A thief with no legal move is captured by enclosure (rule 47). It must own
    # up before doing anything else: the honest answer is the only legal move left.
    if runtime.rules.is_sealed_in(state):
        concede(runtime, claim_response)
        return

    decision = runtime.brain.decide(build_context(runtime))
    if not state.apply_move(decision.move_type, decision.direction, runtime.barriers_max):
        # The chosen action turned out illegal against local truth. Standing still
        # is always legal and keeps the protocol moving; the log records the slip.
        state.apply_move(MoveType.HOLD, None)
        decision.rationale = f"{decision.rationale} [rejected illegal action; held]".strip()
        decision.fallback = True

    win = runtime.rules.thief_result(state)
    capture_claim = _capture_claim(runtime, decision)
    send(runtime, decision, claim_response, capture_claim, {"type": win} if win else None)

    if win:
        runtime.finish(Outcome.SURVIVAL.value, Role.THIEF.value)


def _capture_claim(runtime, decision: Decision):
    """The cell we are accusing, or ``None`` if we are saying nothing.

    Only the officer may claim, and only when the brain deliberately chose to.
    Claiming reveals our exact cell, so it is a move in its own right rather
    than a formality attached to every step.
    """
    if runtime.role is not Role.POLICE or not decision.claims_capture:
        return None
    if decision.move_type is MoveType.BARRIER:
        return runtime.state.last_barrier()
    if decision.move_type is MoveType.MOVE:
        return runtime.state.position
    return None


def send(runtime, decision: Decision, claim_response, capture_claim, win_claim) -> None:
    """Seal the step, refresh our trail and hand the turn token to the opponent."""
    record = sealed_step_record(
        runtime.state, decision, runtime.usage(), runtime.tokens_total,
        extra={
            "opponent_trust": round(runtime.trust.trust, 3),
            "claims_capture": bool(capture_claim),
        },
    )
    runtime.records.append(record)

    runtime.own_scent.deposit(runtime.state.position, runtime.emit_intensity)
    runtime.own_scent.decay_all()
    _feed_credibility_ledger(runtime, decision)

    message = build_turn_message(
        runtime.state, runtime.role.value, decision,
        runtime.own_scent.snapshot(), record["commit"],
        capture_claim=capture_claim, claim_response=claim_response, win_claim=win_claim,
    )
    runtime.transport.send_turn(message.to_dict())
    runtime.emit({"type": "moved", "decision": decision, "commit": record["commit"]})


def _feed_credibility_ledger(runtime, decision: Decision) -> None:
    """Show the bluff planner what our own trail says about the hint we just sent."""
    talker = getattr(runtime.brain, "_talker", None)
    observe = getattr(talker, "observe_sent", None)
    if observe is None:
        return
    evidence = {
        cell: runtime.own_scent.intensity_at(cell) for cell in runtime.own_scent.hot_cells()
    }
    observe(runtime.state.step_number, decision.hint, evidence)


def concede(runtime, claim_response: dict | None) -> None:
    """Admit an enclosure capture: honest, immediate, and sealed like any move."""
    state = runtime.state
    state.apply_move(MoveType.HOLD, None)
    decision = Decision(
        MoveType.HOLD, None, hint=FINAL_CAUGHT_HINT, intent=Intent.TRUTH.value,
        rationale="no legal move remains; conceding capture by enclosure (rule 47)",
    )
    admission = {"claim": list(state.position), "caught": True}
    send(runtime, decision, claim_response or admission, None, None)
    runtime.finish(Outcome.CAPTURE.value, Role.POLICE.value)


def send_final(runtime, claim_response: dict | None) -> None:
    """The mandatory acknowledgement when a capture claim lands on us."""
    decision = Decision(
        MoveType.HOLD, None, hint=FINAL_CAUGHT_HINT, intent=Intent.TRUTH.value,
        rationale="capture claim verified against local truth; answering honestly",
    )
    send(runtime, decision, claim_response, None, None)
