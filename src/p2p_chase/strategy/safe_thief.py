"""``SafeThief`` — evasion with the safety actually proved rather than estimated.

:class:`OpenSpaceThief` scores each candidate cell and vetoes any that finishes
within one step of the believed officer. That veto is right as far as it goes,
and it does not go far enough. It is blind in three ways, and a live series
against uoh-ay26 hit all three:

* **It cannot see a trap.** Judging only where a cell is *now*, it will happily
  step into a cell whose every continuation is covered next turn.
* **It switches itself off.** The veto only applies while belief in one cell
  exceeds a threshold, so precisely when we are least sure where the officer is,
  we stop avoiding it.
* **It gives up when it matters most.** ``_safe_moves(...) or moves`` means that
  if nothing is safe, the safety filter is discarded and the raw score decides.

This class answers the same question by solving it. :mod:`pursuit` backward-
inducts the joint state, so instead of asking "is this cell adjacent to the
officer" we ask "having moved here, for how many plies can the officer be denied
a capture, against best play". The three blind spots close together: a trap is
just a cell with a low ply count, uncertainty is handled by taking the worst
case over everywhere the officer might be, and when nothing is fully safe we
still pick the move that survives longest rather than abandoning the criterion.

Ties are broken by the inherited positional score and then at random. Every
option in that tie is provably as safe as every other, so randomising costs no
safety — and it costs an opponent the ability to predict us, which two
byte-identical sub-games in the last series showed they could.
"""

from p2p_chase.constants import Cell, MoveType, Role
from p2p_chase.strategy import pursuit
from p2p_chase.strategy.base import TurnContext, action_for, candidate_moves
from p2p_chase.strategy.thief_brain import OpenSpaceThief

#: Belief mass below which a cell is not worth defending against. Small enough
#: that a genuinely diffuse belief still widens the threat set rather than
#: collapsing it to the argmax, large enough that numerical dust does not make
#: every cell on the board a threat.
_THREAT_FLOOR = 0.02

#: Most officer positions considered at once. The worst case over the whole
#: support is the ideal; this bounds the cost when belief is near-uniform.
_MAX_THREATS = 12


class SafeThief(OpenSpaceThief):
    """Evasion by proof: maximise the plies the officer cannot capture in."""

    role = Role.THIEF

    def _decide_move(self, context: TurnContext):
        state = context.state
        moves = candidate_moves(context)
        if not moves:
            # No move at all, not even standing still: sealed in, which the book
            # counts as a capture. Denying it would be exposed at the audit.
            return MoveType.HOLD, None, state.position, "sealed in with no legal move", False
        direction, target = self._pick_move(moves, context)
        return action_for(direction), direction, target, self._explain(context, target), False

    def _pick_move(self, moves, context: TurnContext):
        threats = self._threats(context)
        table = pursuit.solve(
            context.state.board,
            context.state.barriers,
            self._horizon(context),
            stay_allowed=context.state.can_stay,
        )
        ranked = [
            (self._safety(table, option[1], threats), self._score(option[1], context), option)
            for option in moves
        ]
        safest = max(item[0] for item in ranked)
        # Only now does the positional score get a say, and only among moves of
        # identical safety. Safety is never traded away for room or distance.
        contenders = [item for item in ranked if item[0] == safest]
        best_score = max(item[1] for item in contenders)
        finalists = [item[2] for item in contenders if item[1] == best_score]
        return self._rng.choice(finalists) if len(finalists) > 1 else finalists[0]

    def _safety(self, table, target: Cell, threats: list[Cell]) -> tuple[int, int, int]:
        """How safe this destination is, worst case first.

        Three numbers, compared in order:

        1. the plies guaranteed against *every* plausible officer — the only one
           that is a guarantee, and the one that decides whenever it can;
        2. how many of those officers the move survives at all;
        3. their total, which separates "briefly safe" from "immediately lost".

        The tie-breakers matter more than they look. When the officer might be on
        any side of us, no move guarantees anything and the worst case is zero
        everywhere; falling straight through to a positional score there once
        made standing still look attractive while it was the one certain loss.
        """
        plies = [table.plies_after_move(target, officer) for officer in threats]
        if not plies:
            return table.depth, 0, 0
        return min(plies), sum(1 for p in plies if p > 0), sum(plies)

    def _threats(self, context: TurnContext) -> list[Cell]:
        """Everywhere the officer plausibly is, not merely where it most likely is.

        Taking the worst case over the support is what replaces the old
        confidence threshold. A sharp belief yields one cell and behaves exactly
        as the veto did; a vague belief yields many and simply demands a move
        that is safe against all of them. There is no longer a confidence level
        at which the thief stops taking the officer into account.
        """
        support = [
            cell
            for cell, mass in context.belief.top_cells(_MAX_THREATS)
            if mass >= _THREAT_FLOOR
        ]
        return support or [context.belief.most_likely()]

    def _horizon(self, context: TurnContext) -> int:
        remaining = max(1, context.steps_remaining)
        return min(remaining, int(self._tune("safety_horizon", pursuit.DEFAULT_HORIZON)))

    def _explain(self, context: TurnContext, cell: Cell) -> str:
        base = super()._explain(context, cell)
        return f"{base} threats={len(self._threats(context))}"
