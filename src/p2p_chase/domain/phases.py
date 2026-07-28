"""The turn state machine (mandatory rules 4 and 5).

A distributed match has exactly one failure mode that cannot be debugged after
the fact: both peers politely waiting for each other forever. A finite state
machine that *refuses* illegal transitions turns that silent deadlock into a
loud exception at the moment the mistake is made.

Legal cycle::

    WAITING_FOR_OPPONENT -> COMPUTING_MOVE -> COMMITTING
        -> AWAITING_REVEAL -> VERIFYING -> WAITING_FOR_OPPONENT

Every communication phase also has an escape hatch to ``TECHNICAL_LOSS``, which
is terminal. That edge is what stops a dropped opponent from hanging the process:
the machine walks out deliberately instead of blocking forever.
"""

from enum import StrEnum

from p2p_chase.exceptions import PhaseError


class Phase(StrEnum):
    """The phases of one turn."""

    WAITING_FOR_OPPONENT = "WAITING_FOR_OPPONENT"
    COMPUTING_MOVE = "COMPUTING_MOVE"
    COMMITTING = "COMMITTING"
    AWAITING_REVEAL = "AWAITING_REVEAL"
    VERIFYING = "VERIFYING"
    AUDITING = "AUDITING"
    GAME_OVER = "GAME_OVER"
    TECHNICAL_LOSS = "TECHNICAL_LOSS"


#: Adjacency list of permitted transitions. Anything absent is rejected.
TRANSITIONS: dict[Phase, frozenset[Phase]] = {
    Phase.WAITING_FOR_OPPONENT: frozenset(
        {Phase.COMPUTING_MOVE, Phase.AUDITING, Phase.TECHNICAL_LOSS}
    ),
    Phase.COMPUTING_MOVE: frozenset({Phase.COMMITTING, Phase.TECHNICAL_LOSS}),
    # COMMITTING -> AUDITING is the "our own move ended the game" edge: the
    # thief's final surviving step, or a conceded enclosure. There is nothing
    # left to await, so we go straight to the reveal.
    Phase.COMMITTING: frozenset({Phase.AWAITING_REVEAL, Phase.AUDITING, Phase.TECHNICAL_LOSS}),
    Phase.AWAITING_REVEAL: frozenset({Phase.VERIFYING, Phase.AUDITING, Phase.TECHNICAL_LOSS}),
    Phase.VERIFYING: frozenset(
        {Phase.WAITING_FOR_OPPONENT, Phase.AUDITING, Phase.TECHNICAL_LOSS}
    ),
    Phase.AUDITING: frozenset({Phase.GAME_OVER, Phase.TECHNICAL_LOSS}),
    Phase.GAME_OVER: frozenset(),
    Phase.TECHNICAL_LOSS: frozenset(),
}

TERMINAL: frozenset[Phase] = frozenset({Phase.GAME_OVER, Phase.TECHNICAL_LOSS})


class GamePhaseMachine:
    """Guards the turn cycle and records the path it took."""

    def __init__(self, start: Phase = Phase.WAITING_FOR_OPPONENT) -> None:
        self.state = start
        self.trail: list[Phase] = [start]

    @property
    def finished(self) -> bool:
        return self.state in TERMINAL

    def can(self, target: Phase) -> bool:
        return target in TRANSITIONS[self.state]

    def to(self, target: Phase) -> Phase:
        """Move to ``target``, or raise :class:`PhaseError` if that edge does not exist."""
        if not self.can(target):
            raise PhaseError(
                f"Illegal phase transition {self.state.value} -> {target.value}; "
                f"legal targets are {sorted(p.value for p in TRANSITIONS[self.state])}"
            )
        self.state = target
        self.trail.append(target)
        return self.state

    def fail(self, reason: str = "") -> Phase:
        """Take the emergency exit to ``TECHNICAL_LOSS`` from any non-terminal phase.

        Used when the network, the opponent or a deadline breaks the turn cycle:
        we would rather record a deliberate technical loss than freeze.
        """
        if self.finished:
            return self.state
        self.reason = reason
        return self.to(Phase.TECHNICAL_LOSS)

    reason: str = ""

    def path(self) -> list[str]:
        return [phase.value for phase in self.trail]
