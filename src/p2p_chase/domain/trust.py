"""Adaptive lie detection: learn how honest this particular opponent is.

The book's central tactical insight is that talk is cheap but scent is not. A
thief may *say* it went north; the pheromone field it leaves behind cannot say
anything but the truth. Cross-referencing the two exposes the lie.

We go one step further than a per-turn contradiction check. Every hint is scored
against the scent evidence and folded into a **Beta-Bernoulli** estimate of
``P(this opponent tells the truth)``:

    alpha, beta  <-  alpha + w * consistent,  beta + w * (1 - consistent)
    trust        =  alpha / (alpha + beta)

The evidence weight ``w`` scales with how much scent mass we actually have, so a
faint, ambiguous field nudges the estimate gently while a blazing contradiction
moves it hard. The resulting ``trust`` feeds straight into
:meth:`BeliefGrid.observe_region`, which means a proven liar's hints are not
discarded — they are *inverted*, and start working for us instead.
"""

from dataclasses import dataclass, field

from p2p_chase.constants import Cell
from p2p_chase.domain.hint_parser import SpatialClaim

#: Beta prior. (1, 1) is a uniform prior over honesty: we assume nothing.
PRIOR_ALPHA = 1.0
PRIOR_BETA = 1.0


@dataclass
class HintVerdict:
    """One hint, scored against the scent evidence."""

    step: int
    consistent: float          # 0.0 = flatly contradicted, 1.0 = fully corroborated
    weight: float              # how much evidence we had (0 = none, so no update)
    trust_after: float
    informative: bool


@dataclass
class TrustEstimator:
    """Running Beta-Bernoulli estimate of an opponent's truthfulness."""

    floor: float = 0.05
    ceiling: float = 0.95
    board_cells: int = 49
    alpha: float = PRIOR_ALPHA
    beta: float = PRIOR_BETA
    history: list[HintVerdict] = field(default_factory=list)

    @property
    def trust(self) -> float:
        """Posterior mean, clamped so we never become certain about a stranger."""
        raw = self.alpha / (self.alpha + self.beta)
        return min(self.ceiling, max(self.floor, raw))

    @property
    def hints_scored(self) -> int:
        return sum(1 for verdict in self.history if verdict.weight > 0)

    @property
    def estimated_lie_rate(self) -> float:
        return round(1.0 - self.trust, 3)

    def score(
        self, step: int, claim: SpatialClaim, scent: dict[Cell, float]
    ) -> HintVerdict:
        """Score one hint against the opponent's scent field and update the estimate.

        ``consistent`` is the share of the opponent's total scent mass that falls
        inside the region it claimed. Standing in a cloud of your own scent in
        the south-east while announcing "heading north" scores near zero.
        """
        if not claim or not scent:
            verdict = HintVerdict(step, 0.5, 0.0, self.trust, bool(claim))
            self.history.append(verdict)
            return verdict

        total = sum(scent.values())
        if total <= 0.0:
            verdict = HintVerdict(step, 0.5, 0.0, self.trust, True)
            self.history.append(verdict)
            return verdict

        inside = sum(value for cell, value in scent.items() if cell in claim.cells)
        share = inside / total
        consistent = share if claim.negated is False else 1.0 - share
        # A claim covering most of the board is trivially "consistent" and proves
        # almost nothing, so the evidence is scaled by how *specific* the claim
        # was: naming one block is a testable assertion, naming half the city is
        # barely one. Scaled again by how much scent there was to test it against.
        specificity = max(0.0, 1.0 - len(claim.cells) / max(1, self.board_cells))
        weight = min(1.0, total) * specificity

        self.alpha += weight * consistent
        self.beta += weight * (1.0 - consistent)
        verdict = HintVerdict(step, round(consistent, 3), round(weight, 3), self.trust, True)
        self.history.append(verdict)
        return verdict

    def summary(self) -> dict:
        """Compact profile for the sealed log and the end-of-match report."""
        return {
            "trust": round(self.trust, 3),
            "estimated_lie_rate": self.estimated_lie_rate,
            "hints_seen": len(self.history),
            "hints_scored": self.hints_scored,
            "alpha": round(self.alpha, 3),
            "beta": round(self.beta, 3),
        }
