"""End-of-game conditions, evaluated by each peer on its *own* state.

No referee exists, so nobody can be told they have lost — they must work it out
and admit it. The book closes that loophole with cryptography rather than trust:
every answer here is sealed, and a peer that denies a capture it actually
suffered is exposed at the audit and forfeits outright (mandatory rules 21-22).

Three ways a thief's run ends, all implemented here:

* the officer steps onto the thief's cell (the classic capture);
* the officer **seals** the thief's cell with a barrier — the book counts that
  as a capture too (mandatory rule 46);
* the thief is walled in with no legal move left, which counts as captured even
  though nobody touched it (mandatory rule 47).
"""

from p2p_chase.constants import Cell, Outcome, Role
from p2p_chase.domain.own_state import OwnGameState


class GameRules:
    """The negotiated end conditions for one sub-game."""

    def __init__(self, survival_threshold: int, max_moves: int | None = None) -> None:
        self.survival_threshold = survival_threshold
        #: Hard ceiling on moves. Defaults to the survival threshold, which is how
        #: the book's own defaults line up (both are 35), but the two are distinct
        #: knobs and an opponent may legitimately negotiate them apart.
        self.max_moves = max_moves if max_moves is not None else survival_threshold

    def thief_result(self, state: OwnGameState) -> str | None:
        """The thief's win claim, if it has earned one this turn."""
        if state.role is not Role.THIEF:
            return None
        if state.step_number >= self.survival_threshold:
            return Outcome.SURVIVAL.value
        return None

    def out_of_moves(self, state: OwnGameState) -> bool:
        """True once the agreed move ceiling is reached, whoever is playing."""
        return state.step_number >= self.max_moves

    @staticmethod
    def is_captured(state: OwnGameState, claim: Cell) -> bool:
        """Answer a capture claim honestly: is my true cell the one being named?

        Lying here buys a single turn and costs the entire match, because the
        sealed record of where we actually stood is revealed minutes later.
        """
        return tuple(state.position) == tuple(claim)

    @staticmethod
    def is_sealed_in(state: OwnGameState) -> bool:
        """True when the thief has been taken by a wall rather than by a step.

        Checked at the *start* of the thief's turn, and covering both walled
        endings the book defines:

        * **rule 46** — a barrier placed on the cell the thief is standing on.
          We used to notice this only when the officer *claimed* the cell, which
          made an honest opponent's silence into our survival. The seal is the
          capture whether or not anyone announces it, and an unclaimed one is
          exactly how a book-true capture gets filed as a survival by two honest
          teams who then contradict each other.
        * **rule 47** — no legal *step* remains. Standing still does not rescue a
          sealed thief; ``is_immobilised`` counts directional moves only.

        A thief that cannot move has already lost, so passing the turn instead
        would let a perfectly executed enclosure fizzle into a survival win.
        """
        if state.role is not Role.THIEF:
            return False
        return tuple(state.position) in state.barriers or state.is_immobilised()

    def evaluate_self(self, state: OwnGameState) -> str | None:
        """The terminal condition this peer must declare about itself, if any.

        Returns ``"capture"`` when the thief must admit it is sealed in,
        ``"survival"`` when it has outlasted the threshold, otherwise ``None``.
        """
        if self.is_sealed_in(state):
            return Outcome.CAPTURE.value
        return self.thief_result(state)
