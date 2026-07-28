"""``BrainBase`` — the contract every strategy implements.

One turn, two decisions, deliberately taken by two different mechanisms:

``_decide_move``
    Pure Python. Returns a legal action or nothing. This is the graded seam and
    the only thing that determines the result on the board.

``talker.say``
    The natural-language hint. May be a template, may be a model, may be a lie —
    and cannot make an illegal move happen, because by the time it runs the move
    is already chosen.

A subclass that overrides ``_pick_move`` gets sensible defaults for everything
else; a subclass that wants full control overrides ``_decide_move``.
"""

import random
import time
from dataclasses import dataclass, field

from p2p_chase.constants import Cell, Direction, Intent, MoveType, Role
from p2p_chase.domain.belief import BeliefGrid
from p2p_chase.domain.own_state import OwnGameState
from p2p_chase.domain.trust import TrustEstimator


@dataclass
class TurnContext:
    """Everything a brain is allowed to know when it decides.

    Assembling this explicitly — rather than handing the brain the whole runtime
    — is what guarantees a strategy cannot accidentally consult the opponent's
    private state: there is no path from here to it.
    """

    state: OwnGameState
    belief: BeliefGrid
    trust: TrustEstimator
    opponent_hint: str = ""
    setting: str = ""
    barriers_max: int = 0
    steps_remaining: int = 0
    deadline_seconds: float | None = None
    tuning: dict = field(default_factory=dict)


@dataclass
class Decision:
    """What the brain chose, and the paper trail behind it."""

    move_type: MoveType
    direction: Direction | None
    hint: str = ""
    intent: str = Intent.TRUTH.value
    target: Cell | None = None
    rationale: str = ""
    prompt_text: str = ""
    reasoning: str = ""
    response_seconds: float = 0.0
    fallback: bool = False
    claims_capture: bool = False

    @property
    def verdict(self) -> str:
        """Wire-compatible alias: the reference protocol calls the intent flag ``verdict``."""
        return self.intent


class BrainBase:
    """Base decision policy. Subclasses override ``_pick_move`` or ``_decide_move``."""

    role: Role

    def __init__(self, rng: random.Random | None = None, talker=None, tuning: dict | None = None):
        self._rng = rng or random.Random()
        self._talker = talker
        self.tuning = tuning or {}

    def decide(self, context: TurnContext) -> Decision:
        """Choose the move in Python, then dress it in words."""
        choice = self._decide_move(context)
        move_type, direction, target, rationale = choice[:4]
        claims = bool(choice[4]) if len(choice) > 4 else False
        started = time.perf_counter()
        hint, intent, reasoning, prompt = self._speak(context, target)
        return Decision(
            move_type=move_type,
            direction=direction,
            hint=hint,
            intent=intent,
            target=target,
            rationale=rationale,
            prompt_text=prompt,
            reasoning=reasoning,
            response_seconds=round(time.perf_counter() - started, 3),
            fallback=move_type is MoveType.HOLD and direction is None,
            claims_capture=claims,
        )

    def _speak(self, context: TurnContext, target: Cell | None) -> tuple[str, str, str, str]:
        if self._talker is None:
            return "", Intent.TRUTH.value, "", ""
        return self._talker.say(self.role, context, target)

    def _decide_move(
        self, context: TurnContext
    ) -> tuple[MoveType, Direction | None, Cell | None, str]:
        """Default policy: take the step ``_pick_move`` likes best, else stand still."""
        moves = context.state.board.legal_moves(context.state.position, context.state.barriers)
        if not moves:
            return MoveType.HOLD, None, None, "no legal move remains"
        direction, target = self._pick_move(moves, context)
        return MoveType.MOVE, direction, target, ""

    def _pick_move(
        self, moves: list[tuple[Direction, Cell]], context: TurnContext
    ) -> tuple[Direction, Cell]:
        raise NotImplementedError

    def _tune(self, key: str, default: float) -> float:
        """Read a tuning knob from config, falling back to a documented default."""
        try:
            return float(self.tuning.get(key, default))
        except (TypeError, ValueError):
            return default
