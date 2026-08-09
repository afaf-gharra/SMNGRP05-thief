"""The capture exchange must be sealed on both sides, not merely announced.

A capture is decided by two messages: the officer names a cell, the thief answers
honestly. If only the live messages carry them, either half can be retold once the
result is known — and the audit, which exists precisely to stop that, has nothing
to check against.
"""

from p2p_chase.constants import Intent, MoveType, Role
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
        Decision(MoveType.HOLD, None, hint="found you", intent=Intent.TRUTH.value),
        None, (6, 5), None,
    )

    payload = _sealed_payload(runtime)
    assert payload["capture_claim"] == [6, 5]
    assert payload["claims_capture"] is True
    assert runtime.transport.sent[-1]["capture_claim"] == [6, 5]


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
