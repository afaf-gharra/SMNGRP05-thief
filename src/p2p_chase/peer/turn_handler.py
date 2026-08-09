"""Folding an opponent's turn message into what this peer knows.

Everything a peer ever learns about its opponent flows through this one method.
There is no shared board to consult, so the entire epistemology of the agent is
these few lines: a decaying scent field, a public barrier declaration, a sentence
that may be a lie, and the answer to a capture claim.

Order matters and is not arbitrary:

1. record any declared barrier — it changes the graph everything else is
   computed on;
2. **predict** — the opponent moved since we last looked, so diffuse the belief
   along the moves actually available to it;
3. **update** — sharpen with the scent field, which cannot lie;
4. cross-examine the words against that same scent, update how much this
   opponent's word is worth, and only then let the words move the belief at all.

Doing (4) after (3) is the whole trick: evidence first, testimony second, and
testimony weighted by a track record built from evidence.
"""

from dataclasses import dataclass

from p2p_chase.constants import Cell, Role
from p2p_chase.domain.hint_parser import parse_hint
from p2p_chase.domain.protocol import TurnMessage


@dataclass
class IncomingOutcome:
    """What an incoming message means for the match."""

    i_won: bool = False                  # they confirmed my capture claim
    i_am_caught: bool = False            # their claim landed on my true cell
    opponent_won: bool = False           # they raised a win claim
    win_type: str | None = None
    claim_response: dict | None = None   # the honest answer I owe them
    hint_verdict: dict | None = None     # what the lie detector made of their words


class TurnHandler:
    """Applies opponent messages to belief, scent, barriers and trust."""

    def __init__(self, state, belief, opponent_scent, rules, trust, landmarks=None,
                 tracker=None):
        self.state = state
        self.belief = belief
        self.opponent_scent = opponent_scent
        self.rules = rules
        self.trust = trust
        self.landmarks = landmarks or {}
        self.tracker = tracker
        self.history: list[dict] = []

    def process(self, message: TurnMessage) -> IncomingOutcome:
        self.history.append(message.to_dict())

        if message.barrier_placed:
            self.state.note_barrier(tuple(message.barrier_placed))

        self.belief.predict(self.state.barriers, stay_allowed=self.state.can_stay)
        self._observe_scent(message.smell_grid)
        self.opponent_scent.absorb(message.smell_grid)
        self.opponent_scent.decay_all()

        outcome = IncomingOutcome()
        outcome.hint_verdict = self._weigh_words(message)
        self._rule_out_impossible()
        self._read_claims(message, outcome)
        return outcome

    def _observe_scent(self, grid: dict) -> None:
        """Fold in the scent field, as sharply as its integrity allows.

        The field's peak is the opponent's current cell whenever the agreed
        pheromone model is being followed, so while the readings stay consistent
        with the signed start, one step per turn and the public wall set, we take
        that shape at close to face value. The moment a field contradicts that
        geometry we stop trusting the shape and fall back to the gentle weighting,
        which cannot be steered by a doctored peak.
        """
        if self.tracker is None:
            self.belief.observe_smell(grid)
            return
        decoded = self.tracker.update(grid, self.state.barriers)
        if decoded.trusted and decoded.cell is not None:
            self.belief.observe_scent_peak(grid)
        else:
            self.belief.observe_smell(grid)

    @property
    def opponent_cell(self) -> tuple | None:
        """Where the scent says the opponent is, or ``None`` if we cannot trust it."""
        if self.tracker is None or not self.tracker.trusted:
            return None
        return self.tracker.cell

    def _weigh_words(self, message: TurnMessage) -> dict | None:
        """Score the hint against their own scent, then let it move the belief."""
        claim = parse_hint(message.hint, self.state.board, self.landmarks)
        evidence: dict[Cell, float] = {
            cell: self.opponent_scent.intensity_at(cell)
            for cell in self.opponent_scent.hot_cells()
        }
        verdict = self.trust.score(message.step, claim, evidence)
        if claim:
            self.belief.observe_region(claim.cells, self.trust.trust)
        return {
            "step": verdict.step,
            "consistent": verdict.consistent,
            "weight": verdict.weight,
            "trust_after": round(verdict.trust_after, 3),
            "informative": verdict.informative,
        }

    def _rule_out_impossible(self) -> None:
        """My own cell and every barrier are cells the opponent cannot be on.

        Small, free, and surprisingly effective late in a match: as the officer
        walls the board in, the set of impossible cells grows fast and the belief
        concentrates without any new observation at all.
        """
        self.belief.exclude_all({self.state.position, *self.state.barriers})

    def _read_claims(self, message: TurnMessage, outcome: IncomingOutcome) -> None:
        if message.claim_response and message.claim_response.get("caught"):
            outcome.i_won = True
        if message.win_claim:
            outcome.opponent_won = True
            outcome.win_type = message.win_claim.get("type")
        if message.capture_claim:
            claimed = tuple(message.capture_claim)
            caught = self.rules.is_captured(self.state, claimed)
            outcome.claim_response = {"claim": list(claimed), "caught": caught}
            outcome.i_am_caught = caught
            if not caught and self.state.role is Role.THIEF:
                # A capture claim is a declaration of the officer's own cell: it
                # can only claim the square it just stepped onto. That makes the
                # claim a free, exact position fix — worth far more than the
                # scent field it came with. Reference implementations claim on
                # *every* move, which hands this over each turn; we take it.
                self.belief.collapse_to(claimed)
