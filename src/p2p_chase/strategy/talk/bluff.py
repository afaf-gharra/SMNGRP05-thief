"""Credibility banking: deciding *when* to lie, not just whether to.

A naive bluffer lies at a fixed rate and is trivially beaten, because the scent
field it leaves behind contradicts every geographic claim it makes. After three
or four turns the opponent's lie detector has it profiled, and from then on its
hints are worse than silence — an opponent who knows you always lie simply
inverts everything you say.

So this planner treats credibility as a resource with a balance:

* It runs the opponent's own detector **on itself**, scoring each hint we send
  against the scent we are visibly leaving. That is a defensible estimate of what
  the opponent now believes about our honesty, computed from information we
  genuinely have.
* When that estimate is low, we tell the truth — cheap, since a true hint about
  a cell the opponent could smell anyway gives away little — and the balance
  recovers.
* When the balance is healthy *and* the moment matters (the endgame, or a turn
  where the opponent is close), we spend it on one decisive lie.
* When a lie would be blatantly contradicted by our own fresh trail, we say
  something spatially empty instead. A vague sentence is not a wasted turn: it
  costs nothing and keeps the balance intact.
"""

from dataclasses import dataclass

from p2p_chase.constants import Cell, Intent
from p2p_chase.domain.board import Board
from p2p_chase.domain.hint_parser import parse_hint
from p2p_chase.domain.trust import TrustEstimator

#: Below this self-estimated credibility, stop bluffing and rebuild trust.
REBUILD_BELOW = 0.45
#: Above this, we can afford a lie without becoming predictable.
SPEND_ABOVE = 0.55


@dataclass
class BluffChoice:
    """What kind of thing to say this turn, and why."""

    intent: str
    sector: str
    credibility: float
    reason: str

    @property
    def lying(self) -> bool:
        return self.intent == Intent.LIE.value


class BluffPlanner:
    """Chooses truth, lie or vagueness, and tracks our own perceived honesty."""

    def __init__(self, board: Board, setting: str, lie_rate: float = 0.45, rng=None) -> None:
        self._board = board
        self._setting = setting
        self._lie_rate = max(0.0, min(1.0, lie_rate))
        self._rng = rng
        self._self_model = TrustEstimator(board_cells=board.cells)
        self._landmarks: dict[str, Cell] = {}

    @property
    def credibility(self) -> float:
        """Our best estimate of ``P(opponent believes our next hint)``."""
        return self._self_model.trust

    def bind_landmarks(self, landmarks: dict[str, Cell]) -> None:
        self._landmarks = landmarks

    def choose(
        self, true_sector: str, decoy_sector: str, urgency: float, step: int
    ) -> BluffChoice:
        """Pick this turn's intent.

        ``urgency`` in ``[0, 1]`` is how much this particular turn is worth
        deceiving on — high in the endgame, high when the opponent is close.
        """
        credibility = self.credibility
        if credibility < REBUILD_BELOW:
            return BluffChoice(
                Intent.TRUTH.value, true_sector, credibility,
                "credibility spent; telling the truth to rebuild it",
            )
        appetite = self._lie_rate * (0.5 + urgency)
        if credibility >= SPEND_ABOVE and self._roll() < appetite:
            return BluffChoice(
                Intent.LIE.value, decoy_sector, credibility,
                f"spending credibility {credibility:.2f} on a decoy (urgency {urgency:.2f})",
            )
        return BluffChoice(
            Intent.TRUTH.value, true_sector, credibility,
            "banking credibility with a true hint",
        )

    def observe_own_hint(self, step: int, hint: str, own_scent: dict[Cell, float]) -> float:
        """Score a hint we just sent exactly as the opponent's detector will.

        This is the feedback loop that makes the balance real rather than
        assumed: a lie that our own trail flatly contradicts costs credibility
        immediately, and the planner sees the bill on the next turn.
        """
        claim = parse_hint(hint, self._board, self._landmarks)
        self._self_model.score(step, claim, own_scent)
        return self.credibility

    def summary(self) -> dict:
        """Folded into the sealed log so the bluffing policy is auditable."""
        model = self._self_model.summary()
        return {
            "self_credibility": round(self.credibility, 3),
            "target_lie_rate": self._lie_rate,
            "hints_sent": model["hints_seen"],
            "hints_falsifiable": model["hints_scored"],
        }

    def _roll(self) -> float:
        return self._rng.random() if self._rng is not None else 0.5


def urgency_of(steps_remaining: int, total_steps: int, threat_distance: int, board_size: int) -> float:
    """How much this turn is worth lying on, in ``[0, 1]``.

    Two things raise the stakes: the clock running down, and the opponent being
    close enough that one misdirected step actually changes the outcome.
    """
    clock = 1.0 - min(1.0, max(0, steps_remaining) / max(1, total_steps))
    proximity = 1.0 - min(1.0, max(0, threat_distance) / max(1, board_size))
    return round(min(1.0, 0.5 * clock + 0.5 * proximity), 3)
