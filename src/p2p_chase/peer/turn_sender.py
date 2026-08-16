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
    """The cell the officer declares after acting — every turn, without exception.

    This used to be gated on ``decision.claims_capture``, on the reasoning that
    naming our square gives our position away and should therefore be a
    deliberate act. That gate was a straight loss. The scent field we send in
    the *same message* peaks on the cell we occupy, so an opponent who decodes
    it already knows exactly where we are — which is precisely how uoh-ay26 beat
    us 30–90. The gate leaked nothing extra and cost us captures.

    Cost us how: an unclaimed step onto the thief is not a capture anywhere.
    Our own handler only ever sets ``i_am_caught`` from an incoming claim, the
    course reference claims on every move, and uoh-ay26 state the rule outright
    — coordinate equality is never converted into a capture retroactively at
    the audit. So an officer that walks onto the thief while under-confident
    simply fails to win a sub-game it had already won.

    Barrier turns keep naming the wall rather than our feet: sealing the thief
    in *is* the capture under rule 46, and the reference peer's thief answers
    only what arrives in ``capture_claim``. Peers that also check the separately
    published ``barrier_placed`` reach the same verdict by the other route.
    """
    if runtime.role is not Role.POLICE:
        return None
    if decision.move_type is MoveType.BARRIER:
        return runtime.state.last_barrier() or runtime.state.position
    return runtime.state.position


def send(runtime, decision: Decision, claim_response, capture_claim, win_claim) -> None:
    """Seal the step, refresh our trail and hand the turn token to the opponent."""
    record = sealed_step_record(
        runtime.state, decision, runtime.usage(), runtime.tokens_total,
        extra={
            "opponent_trust": round(runtime.trust.trust, 3),
            # The brain's *intent*, not the wire field. The officer now names its
            # square every turn, so ``bool(capture_claim)`` is always true for
            # police and would record nothing; this keeps the log able to say
            # which of those declarations was a considered accusation.
            "claims_capture": bool(decision.claims_capture),
            # Both halves of the capture exchange are sealed, not just announced.
            # A claim binds the accuser to the cell it named; the answer binds us
            # to the admission. Sealing only one side lets the unsealed half be
            # retold after the result is known, which is the one thing the audit
            # exists to prevent.
            "capture_claim": list(capture_claim) if capture_claim else None,
            "claim_response": claim_response,
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
    """The mandatory acknowledgement when a capture claim lands on us.

    The admission is a *turn*, not an annotation on the last one, so it advances
    the step counter exactly as :func:`concede` does. Without the hold this
    message would carry the step number we already sent, and an opponent that
    had consumed that step sees the same (role, step) arrive twice — reading it
    as a duplicated retry and refusing it, so the capture is never acknowledged
    and an already-decided sub-game dies of a timeout instead.
    """
    runtime.state.apply_move(MoveType.HOLD, None)
    decision = Decision(
        MoveType.HOLD, None, hint=FINAL_CAUGHT_HINT, intent=Intent.TRUTH.value,
        rationale="capture claim verified against local truth; answering honestly",
    )
    send(runtime, decision, claim_response, None, None)
