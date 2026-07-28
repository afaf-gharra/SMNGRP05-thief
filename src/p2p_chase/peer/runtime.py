"""``PeerRuntime`` — one autonomous agent playing one sub-game.

The lifecycle is: agree terms, then alternate between waiting for the opponent's
turn and taking our own, until somebody wins or the protocol breaks. Every phase
change goes through the state machine, so an impossible sequence raises instead
of hanging, and every wait carries a deadline, so a vanished opponent costs one
timeout rather than the afternoon.

The runtime deliberately owns *state*, not *policy*: what to do on a turn lives
in :mod:`p2p_chase.strategy`, what a message means lives in
:mod:`p2p_chase.peer.turn_handler`, and how to reach the opponent lives in
:mod:`p2p_chase.infra`. This file only decides when each of them runs.
"""

import random
import time

from p2p_chase.constants import Outcome, Role
from p2p_chase.domain.belief import BeliefGrid
from p2p_chase.domain.own_state import OwnGameState
from p2p_chase.domain.phases import GamePhaseMachine, Phase
from p2p_chase.domain.protocol import TurnMessage
from p2p_chase.domain.rules import GameRules
from p2p_chase.domain.smell import SmellField
from p2p_chase.domain.trust import TrustEstimator
from p2p_chase.peer import turn_sender
from p2p_chase.peer.deadline import DeadlineTracker
from p2p_chase.peer.handshake import negotiate
from p2p_chase.peer.sealing import identity_from_config, now_iso, sealed_spec_record
from p2p_chase.peer.summary import build_summary, live_view
from p2p_chase.peer.turn_handler import TurnHandler
from p2p_chase.strategy.factory import resolve_brain
from p2p_chase.strategy.talk import landmarks as geo
from p2p_chase.strategy.talk.factory import resolve_talker


class PeerRuntime:
    """One agent, one sub-game, no referee."""

    def __init__(self, role, config, transport, sub_game_number=1, listener=None,
                 own_identity=None, watchdog=None, repo_root=None):
        self.role = Role(role)
        self.config = config
        self.transport = transport
        self.sub_game_number = sub_game_number
        self._listener = listener or (lambda event: None)
        self.watchdog = watchdog
        self.own_identity = own_identity or identity_from_config(config)
        self.peer_identity: dict = {}
        self.game_id: str | None = None
        self.game_uid: str | None = None

        size = config.require("board.size")
        start = tuple(config.require(f"positions.{'thief' if self.role is Role.THIEF else 'cop'}_start"))
        self.state = OwnGameState(self.role, start, size, config.get("rules.move_set"))
        self.barriers_max = int(config.get("rules.barriers_max", 0))
        self.state.set_quota(self.barriers_max)
        self.emit_intensity = float(config.require("smell.emit_intensity"))

        self.belief = BeliefGrid(self.state.board, config.get("belief.smell_trust_weight", 4.0))
        self.opponent_scent = self._field(config, size)
        self.own_scent = self._field(config, size)
        self.trust = TrustEstimator(
            floor=config.get("belief.hint_trust_floor", 0.05),
            ceiling=config.get("belief.hint_trust_ceiling", 0.95),
            board_cells=self.state.board.cells,
        )
        self.rules = GameRules(
            config.require("rules.survival_threshold"), config.get("rules.max_moves")
        )
        self.handler = TurnHandler(
            self.state, self.belief, self.opponent_scent, self.rules, self.trust,
            landmarks=geo.landmark_index(self.state.board, config.get("play.setting", "") or ""),
        )
        rng = random.Random(config.get("play.seed"))
        talker = resolve_talker(config, self.state.board, rng)
        self.brain = resolve_brain(config, self.role, talker=talker, rng=rng)
        self.talker = talker

        self.phases = GamePhaseMachine()
        self.deadlines = DeadlineTracker(config.get("network.turn_timeout_seconds", 180))
        self.records: list[dict] = [sealed_spec_record(config, sub_game_number, repo_root)]
        self.tokens_total = 0
        self.audit: dict = {}
        self.started_at = now_iso()
        self._started = time.monotonic()
        self._result: tuple[str, str] | None = None

    @staticmethod
    def _field(config, size: int) -> SmellField:
        return SmellField(
            board_size=size,
            grid_size=config.require("smell.grid_size"),
            decay=config.require("smell.decay_per_step"),
            min_center=config.get("smell.min_center_intensity", 0.0),
            falloff=config.get("smell.falloff", "linear"),
        )

    # ------------------------------------------------------------------ hooks

    def emit(self, event: dict) -> None:
        """Publish an event, and follow it with the current local-truth view.

        The view is emitted as a separate event so a consumer that only cares
        about, say, capture claims can ignore it, while the live window gets a
        repaint after every state change without the runtime knowing a GUI exists.
        """
        base = {"role": self.role.value, "step": self.state.step_number}
        self._listener({**event, **base})
        self._listener({"type": "view", "view": live_view(self), **base})

    def usage(self) -> dict:
        used = int(getattr(self.talker, "tokens_used", 0) or 0)
        step_cost = max(0, used - self.tokens_total)
        self.tokens_total = used
        return {"model": self.config.get("llm.model", "template-zero-token"), "total": step_cost}

    def finish(self, result: str, winner: str) -> None:
        if self._result is None:
            self._result = (result, winner)

    @property
    def result(self) -> tuple[str, str] | None:
        return self._result

    # ------------------------------------------------------------------- run

    def run(self) -> dict:
        """Play one sub-game to a conclusion and return its summary."""
        negotiate(self)
        self.emit({"type": "negotiated", "game_id": self.game_id})
        if self.role is Role.THIEF:
            self._act(claim_response=None)  # the thief opens
        self._loop()
        self._audit()
        return build_summary(self)

    def _act(self, claim_response: dict | None) -> None:
        self.phases.to(Phase.COMPUTING_MOVE)
        turn_sender.take_turn(self, claim_response)
        self.phases.to(Phase.COMMITTING)
        if self._result is None:
            self.phases.to(Phase.AWAITING_REVEAL)

    def _loop(self) -> None:
        poll = float(self.config.get("network.poll_interval_seconds", 0.5))
        while self._result is None:
            if self.watchdog is not None:
                self.watchdog.beat()
            deadline = self.deadlines.start("opponent_turn")
            incoming = self._await_turn(deadline, poll)
            if incoming is None:
                self.deadlines.record(deadline)
                self.phases.fail("opponent went silent past the turn deadline")
                self.finish(Outcome.TIMEOUT.value, self.role.value)
                return
            self.deadlines.record(deadline)
            self._consume(incoming)

    def _await_turn(self, deadline, poll: float) -> dict | None:
        while not deadline.expired:
            message = self.transport.poll_turn(min(poll, max(0.05, deadline.remaining)))
            if message is not None:
                return message
            if self.watchdog is not None:
                self.watchdog.beat()
        return None

    def _consume(self, incoming: dict) -> None:
        if self.phases.state is Phase.AWAITING_REVEAL:
            self.phases.to(Phase.VERIFYING)
            self.phases.to(Phase.WAITING_FOR_OPPONENT)
        outcome = self.handler.process(TurnMessage.from_dict(incoming))
        self.emit({"type": "incoming", "message": incoming, "verdict": outcome.hint_verdict})
        if outcome.i_won:
            self.finish(Outcome.CAPTURE.value, Role.POLICE.value)
        elif outcome.opponent_won:
            self.finish(outcome.win_type or Outcome.SURVIVAL.value, Role.THIEF.value)
        elif outcome.i_am_caught:
            turn_sender.send_final(self, outcome.claim_response)
            self.finish(Outcome.CAPTURE.value, Role.POLICE.value)
        else:
            self._act(outcome.claim_response)

    def _audit(self) -> None:
        from p2p_chase.peer.audit import exchange_audit

        if not self.phases.finished:
            self.phases.to(Phase.AUDITING)
        self.audit = exchange_audit(self)
        if not self.phases.finished:
            self.phases.to(Phase.GAME_OVER)

    @property
    def duration_seconds(self) -> float:
        return round(time.monotonic() - self._started, 2)
