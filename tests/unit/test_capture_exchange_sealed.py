"""The capture exchange must be sealed on both sides, not merely announced.

A capture is decided by two messages: the officer names a cell, the thief answers
honestly. If only the live messages carry them, either half can be retold once the
result is known — and the audit, which exists precisely to stop that, has nothing
to check against.
"""

from p2p_chase.constants import Direction, Intent, MoveType, Role
from p2p_chase.peer import turn_sender
from p2p_chase.peer.world import build_world
from p2p_chase.strategy.base import Decision


class _Recorder:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send_turn(self, message: dict) -> None:
        self.sent.append(message)


class _Runtime:
    def __init__(self, config, role: Role) -> None:
        world = build_world(role, config)
        self.role = role
        self.config = config
        self.state = world.state
        self.own_scent = world.own_scent
        self.trust = world.trust
        self.brain = world.brain
        self.emit_intensity = world.emit_intensity
        self.transport = _Recorder()
        self.records: list[dict] = []
        self.tokens_total = 0
        self._result = None

    def usage(self) -> dict:
        return {"model": "template-zero-token", "total": 0}

    def emit(self, event: dict) -> None:
        pass

    def finish(self, result: str, winner: str) -> None:
        self._result = (result, winner)


def _sealed_payload(runtime) -> dict:
    return runtime.records[-1]["payload"]


def test_the_admission_is_sealed_not_only_announced(config):
    runtime = _Runtime(config, Role.THIEF)
    answer = {"claim": [3, 3], "caught": True}

    turn_sender.send_final(runtime, answer)

    assert _sealed_payload(runtime)["claim_response"] == answer
    assert runtime.transport.sent[-1]["claim_response"] == answer


def test_an_honest_denial_is_sealed_too(config):
    """A false claim must be as auditable as a true one."""
    runtime = _Runtime(config, Role.THIEF)
    answer = {"claim": [0, 0], "caught": False}

    runtime.state.apply_move(MoveType.HOLD, None)
    turn_sender.send(
        runtime,
        Decision(MoveType.HOLD, None, hint="not me", intent=Intent.TRUTH.value),
        answer, None, None,
    )

    assert _sealed_payload(runtime)["claim_response"] == answer


def test_the_officers_claim_is_sealed_with_the_cell_it_named(config):
    runtime = _Runtime(config, Role.POLICE)
    runtime.state.apply_move(MoveType.HOLD, None)

    turn_sender.send(
        runtime,
        Decision(MoveType.HOLD, None, hint="found you", intent=Intent.TRUTH.value,
                 claims_capture=True),
        None, (6, 5), None,
    )

    payload = _sealed_payload(runtime)
    assert payload["capture_claim"] == [6, 5]
    assert payload["claims_capture"] is True
    assert runtime.transport.sent[-1]["capture_claim"] == [6, 5]


# ------------------------------------------------- the officer names every square


def test_the_officer_names_its_cell_even_when_it_is_not_accusing(config):
    """An unclaimed step onto the thief is not a capture anywhere.

    Our own handler sets ``i_am_caught`` only from an incoming claim, the course
    reference claims on every move, and uoh-ay26 publish the rule explicitly:
    coordinate equality is never converted into a capture at the audit. Gating
    the claim on confidence therefore threw away sub-games we had already won.
    """
    runtime = _Runtime(config, Role.POLICE)
    runtime.state.apply_move(MoveType.MOVE, Direction.E)

    quiet = Decision(MoveType.MOVE, Direction.E, hint="walking", intent=Intent.TRUTH.value)
    assert quiet.claims_capture is False

    assert turn_sender._capture_claim(runtime, quiet) == runtime.state.position


def test_a_holding_officer_still_names_its_cell(config):
    """STAY is an action, and the thief may have stepped onto us during it."""
    runtime = _Runtime(config, Role.POLICE)
    runtime.state.apply_move(MoveType.HOLD, None)

    decision = Decision(MoveType.HOLD, None, hint="waiting", intent=Intent.TRUTH.value)
    assert turn_sender._capture_claim(runtime, decision) == runtime.state.position


def test_a_barrier_turn_names_the_wall_not_our_feet(config):
    """Sealing the thief in is the capture (rule 46), and the reference peer's
    thief answers only what arrives in ``capture_claim``."""
    runtime = _Runtime(config, Role.POLICE)
    runtime.state.apply_move(MoveType.BARRIER, Direction.E, 14)

    decision = Decision(MoveType.BARRIER, Direction.E, hint="walling", intent=Intent.TRUTH.value)
    claim = turn_sender._capture_claim(runtime, decision)

    assert claim == runtime.state.last_barrier()
    assert claim != runtime.state.position


def test_the_thief_never_claims(config):
    """Only the officer may accuse; a claiming thief is a protocol violation."""
    runtime = _Runtime(config, Role.THIEF)
    runtime.state.apply_move(MoveType.MOVE, Direction.E)

    decision = Decision(MoveType.MOVE, Direction.E, hint="running", intent=Intent.TRUTH.value,
                        claims_capture=True)
    assert turn_sender._capture_claim(runtime, decision) is None


def test_the_sealed_log_still_distinguishes_a_considered_accusation(config):
    """``claims_capture`` records the brain's intent, not the wire field, which
    is now always set for police and would otherwise record nothing."""
    runtime = _Runtime(config, Role.POLICE)
    runtime.state.apply_move(MoveType.HOLD, None)

    turn_sender.send(
        runtime,
        Decision(MoveType.HOLD, None, hint="routine", intent=Intent.TRUTH.value),
        None, runtime.state.position, None,
    )

    payload = _sealed_payload(runtime)
    assert payload["capture_claim"] == list(runtime.state.position)
    assert payload["claims_capture"] is False


def test_a_quiet_turn_seals_both_fields_as_null(config):
    """Explicit nulls, so a later insertion cannot masquerade as an old record."""
    runtime = _Runtime(config, Role.THIEF)
    runtime.state.apply_move(MoveType.HOLD, None)

    turn_sender.send(
        runtime,
        Decision(MoveType.HOLD, None, hint="quiet", intent=Intent.TRUTH.value),
        None, None, None,
    )

    payload = _sealed_payload(runtime)
    assert payload["capture_claim"] is None
    assert payload["claim_response"] is None


def test_the_sealed_admission_still_verifies_against_its_commit(config):
    from p2p_chase.domain.crypto import CommitReveal

    runtime = _Runtime(config, Role.THIEF)
    turn_sender.send_final(runtime, {"claim": [3, 3], "caught": True})

    record = runtime.records[-1]
    CommitReveal.verify(record["payload"], record["nonce"], record["commit"])
