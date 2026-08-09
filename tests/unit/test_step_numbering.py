"""Every outbound message must carry a step number we have not already used.

An opponent tracks turns by ``(role, step)``. Re-using a number makes an honest
new message indistinguishable from a duplicated retry, and a peer that dedupes
correctly will discard it — so a capture acknowledgement never lands and a
sub-game that was already decided dies of a timeout instead.
"""

from p2p_chase.constants import Intent, MoveType, Role
from p2p_chase.peer import turn_sender
from p2p_chase.peer.world import build_world
from p2p_chase.strategy.base import Decision


class _Recorder:
    """Captures what would have gone on the wire."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send_turn(self, message: dict) -> None:
        self.sent.append(message)


class _Runtime:
    """The slice of PeerRuntime that turn_sender actually touches."""

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


def _hold(runtime) -> None:
    runtime.state.apply_move(MoveType.HOLD, None)
    turn_sender.send(
        runtime,
        Decision(MoveType.HOLD, None, hint="holding", intent=Intent.TRUTH.value),
        None, None, None,
    )


def test_the_capture_acknowledgement_advances_the_step_number(config):
    """The bug an opponent caught: the admission reused the previous step."""
    runtime = _Runtime(config, Role.THIEF)
    _hold(runtime)
    first = runtime.transport.sent[-1]["step"]

    turn_sender.send_final(runtime, {"claim": [3, 3], "caught": True})
    admission = runtime.transport.sent[-1]

    assert admission["step"] == first + 1
    assert admission["claim_response"] == {"claim": [3, 3], "caught": True}


def test_no_step_number_is_ever_sent_twice(config):
    runtime = _Runtime(config, Role.THIEF)
    for _ in range(3):
        _hold(runtime)
    turn_sender.send_final(runtime, {"claim": [3, 3], "caught": True})

    steps = [message["step"] for message in runtime.transport.sent]
    assert steps == sorted(steps), "steps must be monotonically increasing"
    assert len(steps) == len(set(steps)), f"a step number was reused: {steps}"


def test_conceding_by_enclosure_also_advances_the_step(config):
    runtime = _Runtime(config, Role.THIEF)
    _hold(runtime)
    before = runtime.transport.sent[-1]["step"]

    turn_sender.concede(runtime, None)

    assert runtime.transport.sent[-1]["step"] == before + 1
