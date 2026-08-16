"""``Orchestrator`` — the single gateway to every subsystem (mandatory rule 3).

Five subsystems, one door. The transport, the per-sub-game runtime, the deadline
tracker, the watchdog and the report emitter never call each other directly;
they are coordinated from here. The payoff is the one the book insists on: any
of them can be replaced with a double and the rest of the system does not
notice, which is why a whole six-game series can be played in a unit test with
no sockets at all.

The orchestrator coordinates, it does not decide. There is no game logic in this
file — only the order things happen in, and what to do when one of them fails.
"""

import logging

from p2p_chase.constants import Role
from p2p_chase.exceptions import ChaseError, RestartSeries
from p2p_chase.peer.runtime import PeerRuntime
from p2p_chase.peer.sealing import identity_from_config
from p2p_chase.peer.watchdog import Watchdog

logger = logging.getLogger(__name__)

MAX_RESTARTS = 10


def role_for(natural: Role, sub_game_number: int) -> Role:
    """Roles alternate: our natural role on odd sub-games, the other on even ones.

    Both peers apply the same rule to the same index, so they always disagree
    about who is the officer — which is precisely what makes them agree.
    """
    if sub_game_number % 2 == 1:
        return natural
    return Role.THIEF if natural is Role.POLICE else Role.POLICE


class SeriesResult:
    """What a completed series hands to the report layer."""

    def __init__(self, summaries, own_identity, peer_identity, game_id, game_uid):
        self.summaries = summaries
        self.own_identity = own_identity
        self.peer_identity = peer_identity
        self.game_id = game_id
        self.game_uid = game_uid


class Orchestrator:
    """Runs a whole series of sub-games against one opponent."""

    def __init__(self, config, transport, listener=None, repo_root=None):
        self.config = config
        self.transport = transport
        self.listener = listener or (lambda event: None)
        self.repo_root = repo_root
        self.own_identity = identity_from_config(config)
        self.watchdog = Watchdog(
            timeout_seconds=config.get("network.watchdog_timeout_seconds", 300),
            state_dir=config.get("paths.state_dir", "state"),
        )
        self.runtime: PeerRuntime | None = None

    def play_series(self, natural_role: Role) -> SeriesResult:
        """Play every sub-game, restarting the series if the opponent asks."""
        self.watchdog.bind(self._snapshot)
        self.watchdog.start()
        try:
            attempt = 0
            while True:
                try:
                    return self._play_all(natural_role)
                except RestartSeries:
                    attempt += 1
                    if attempt > MAX_RESTARTS:
                        raise
                    logger.info("Series restart requested (attempt %d)", attempt)
                    self.transport.drain_inboxes()
                    self.listener({"type": "series_restart", "attempt": attempt})
        finally:
            self.watchdog.stop()

    def _play_all(self, natural_role: Role) -> SeriesResult:
        total = int(self.config.get("league.num_games", 1))
        summaries: list[dict] = []
        peer_identity: dict = {}
        game_id = game_uid = None

        for index in range(1, total + 1):
            role = role_for(natural_role, index)
            self._dial_role_for(role)
            self.listener({"type": "sub_game_start", "sub_game_number": index, "role": role.value})
            runtime = PeerRuntime(
                role=role, config=self.config, transport=self.transport,
                sub_game_number=index, listener=self.listener,
                own_identity=self.own_identity, watchdog=self.watchdog,
                repo_root=self.repo_root,
            )
            self.runtime = runtime
            summaries.append(self._play_one(runtime, index))
            peer_identity = runtime.peer_identity or peer_identity
            game_id, game_uid = runtime.game_id or game_id, runtime.game_uid or game_uid

        return SeriesResult(summaries, self.own_identity, peer_identity, game_id, game_uid)

    def _dial_role_for(self, own_role: Role) -> None:
        """Aim the transport at whichever of the opponent's servers is playing.

        Teams whose cop and thief are separate programs publish an endpoint per
        role, and roles alternate every sub-game, so the address we dial has to
        alternate with them. Optional on the transport: the in-memory doubles the
        test suite plays whole series through have no notion of a URL.
        """
        aim = getattr(self.transport, "target_role", None)
        if aim is None:
            return
        opponent = Role.THIEF if own_role is Role.POLICE else Role.POLICE
        aim(opponent.value)

    def _play_one(self, runtime: PeerRuntime, index: int) -> dict:
        """Play one sub-game, converting a protocol failure into a scored result.

        A crash here must not lose the whole series: the book scores a technical
        loss at 0-0, which is a *result*, and a series that reports five sub-games
        and one technical loss is worth far more than one that reports nothing.
        """
        from p2p_chase.peer.summary import build_summary

        try:
            return runtime.run()
        except RestartSeries:
            raise
        except ChaseError as exc:
            logger.error("Sub-game %d failed: %s", index, exc)
            runtime.phases.fail(str(exc))
            runtime.finish("tamper_forfeit" if "commit" in str(exc).lower() else "timeout", "-")
            self.listener({"type": "sub_game_failed", "sub_game_number": index, "error": str(exc)})
            summary = build_summary(runtime)
            summary["error"] = str(exc)
            return summary

    def _snapshot(self) -> dict:
        """State the watchdog persists if the main loop stops breathing."""
        if self.runtime is None:
            return {"status": "no sub-game in progress"}
        from p2p_chase.peer.summary import live_view

        return {
            "game_id": self.runtime.game_id,
            "sub_game_number": self.runtime.sub_game_number,
            "phase": self.runtime.phases.state.value,
            "records": self.runtime.records,
            "view": live_view(self.runtime),
        }
