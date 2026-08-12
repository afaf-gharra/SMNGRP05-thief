"""Assemble one sub-game's private world from configuration.

Everything a peer knows about itself and infers about its opponent is built
here, in one place, from the agreed terms: the board and our position on it, the
two scent fields, the belief filter, the honesty model of this particular
opponent, and the rules that decide when it ends.

Split out of :mod:`p2p_chase.peer.runtime` so that file stays about *sequencing*
— when each thing runs — rather than about wiring. It also makes the whole world
constructible in a test without a transport or a network.
"""

import random
from dataclasses import dataclass

from p2p_chase.constants import Role
from p2p_chase.domain.belief import BeliefGrid
from p2p_chase.domain.own_state import OwnGameState
from p2p_chase.domain.rules import GameRules
from p2p_chase.domain.smell import SmellField
from p2p_chase.domain.trust import TrustEstimator
from p2p_chase.peer.turn_handler import TurnHandler
from p2p_chase.strategy.decode import ScentTracker
from p2p_chase.strategy.factory import resolve_brain
from p2p_chase.strategy.talk import landmarks as geo
from p2p_chase.strategy.talk.factory import resolve_talker


@dataclass
class World:
    """One peer's private universe for one sub-game."""

    state: OwnGameState
    belief: BeliefGrid
    own_scent: SmellField
    opponent_scent: SmellField
    trust: TrustEstimator
    rules: GameRules
    handler: TurnHandler
    brain: object
    talker: object
    barriers_max: int
    emit_intensity: float


def build_world(role: Role, config) -> World:
    """Construct the world for ``role`` from the agreed terms.

    ``require`` rather than ``get`` for every agreed term: a missing board size
    must stop us here, before a port is opened, rather than surface as a ``None``
    crash on move seventeen.
    """
    size = config.require("board.size")
    corner = "thief" if role is Role.THIEF else "cop"
    state = OwnGameState(
        role, tuple(config.require(f"positions.{corner}_start")), size,
        config.get("rules.move_set"),
    )
    barriers_max = int(config.get("rules.barriers_max", 0))
    state.set_quota(barriers_max)

    # The opponent's opening cell is an agreed, signed term, so the very first
    # belief is a certainty rather than the uniform shrug we used to start from.
    # Beginning ignorant threw away the one moment in the game when we know
    # exactly where the other agent is, and left the filter with nothing to
    # anchor its first prediction to.
    opponent_start = tuple(config.require(f"positions.{'cop' if role is Role.THIEF else 'thief'}_start"))
    belief = BeliefGrid(state.board, config.get("belief.smell_trust_weight", 4.0))
    belief.collapse_to(opponent_start)
    opponent_scent = _scent_field(config, size)
    trust = TrustEstimator(
        floor=config.get("belief.hint_trust_floor", 0.05),
        ceiling=config.get("belief.hint_trust_ceiling", 0.95),
        board_cells=state.board.cells,
    )
    rules = GameRules(
        config.require("rules.survival_threshold"), config.get("rules.max_moves")
    )
    handler = TurnHandler(
        state, belief, opponent_scent, rules, trust,
        landmarks=geo.landmark_index(state.board, config.get("play.setting", "") or ""),
        tracker=ScentTracker(state.board, expected_start=opponent_start),
    )
    # One RNG seeded from the private config drives both the movement tie-breaks
    # and the banter, so a whole sub-game replays identically from its seed.
    rng = random.Random(config.get("play.seed"))
    talker = resolve_talker(config, state.board, rng)
    return World(
        state=state,
        belief=belief,
        own_scent=_scent_field(config, size),
        opponent_scent=opponent_scent,
        trust=trust,
        rules=rules,
        handler=handler,
        brain=resolve_brain(config, role, talker=talker, rng=rng),
        talker=talker,
        barriers_max=barriers_max,
        emit_intensity=float(config.require("smell.emit_intensity")),
    )


def _scent_field(config, size: int) -> SmellField:
    """A scent field on the agreed emission and decay model.

    Two of these exist per peer and they are deliberately separate: one holds the
    trail we emit and broadcast, the other what we have absorbed from the
    opponent. Merging them would let us smell ourselves and chase our own tail.
    """
    return SmellField(
        board_size=size,
        grid_size=config.require("smell.grid_size"),
        decay=config.require("smell.decay_per_step"),
        min_center=config.get("smell.min_center_intensity", 0.0),
        falloff=config.get("smell.falloff", "linear"),
        decay_mode=config.get("smell.decay_mode", "subtractive"),
    )
