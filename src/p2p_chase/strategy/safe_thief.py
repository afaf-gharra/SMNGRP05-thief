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
        self._solved = {}
        table = self._table(context, frozenset(context.state.barriers))
        ranked = [
            (
                self._safety(table, option[1], threats, context),
                self._score(option[1], context),
                option,
            )
            for option in moves
        ]
        safest = max(item[0] for item in ranked)
        # Only now does the positional score get a say, and only among moves of
        # identical safety. Safety is never traded away for room or distance.
        contenders = [item for item in ranked if item[0] == safest]
        best_score = max(item[1] for item in contenders)
        finalists = [item[2] for item in contenders if item[1] == best_score]
        return self._rng.choice(finalists) if len(finalists) > 1 else finalists[0]

    def _safety(self, table, target: Cell, threats, context) -> tuple[int, int, int, int]:
        """How safe this destination is, worst case first.

        Four numbers, compared in order:

        1. the plies guaranteed against *every* plausible officer, allowing for
           the wall it may build — the only one that is a guarantee;
        2. **how many walls it would take to seal this cell** — its open exits,
           counted only once (1) has saturated at the horizon;
        3. how many of those officers the move survives at all;
        4. their total, which separates "briefly safe" from "immediately lost".

        The second number is the fix for a series we lost 30-90, and it belongs
        here rather than in the positional tie-break where it used to live.
        ``plies`` is computed against the walls that exist *now*, so on an open
        board the far corner scores the full horizon precisely **because** it is
        far away. Every roomy cell scores the same capped number, the corner ties
        with them, and the tie was then broken by a positional score in which
        ``mobility_weight`` could never outvote distance. Our thief walked into
        (6,0), played STAY five times, and was sealed by two walls out of
        fourteen — the same corner, the same two cells, in all three sub-games it
        lost. Exits are cheap to count and they are what the officer is actually
        spending walls against, so they rank above preference and below proof.

        The tie-breakers matter more than they look. When the officer might be on
        any side of us, no move guarantees anything and the worst case is zero
        everywhere; falling straight through to a positional score there once
        made standing still look attractive while it was the one certain loss.
        """
        exits = len(context.state.board.neighbors(target, context.state.barriers))
        plies = [self._against(table, target, officer, context) for officer in threats]
        if not plies:
            return table.depth, exits, 0, 0
        worst = min(plies)
        # Room counts ONLY where the ply count has saturated, and nowhere else.
        # At the horizon every roomy cell and every corner report the same capped
        # number, so the first key has stopped discriminating and exits are the
        # honest way to separate them. Below the cap we are already losing, and
        # the question becomes which move loses slowest; two tests caught the
        # cost of forgetting that -- ranking room any lower in the tuple traded a
        # cell that survives another ply for a roomier one that dies at once.
        room = exits if worst >= table.depth else 0
        return worst, room, sum(1 for p in plies if p > 0), sum(plies)

    def _against(self, table, target: Cell, officer: Cell, context) -> int:
        """Plies survived against one officer, including the wall it might build.

        The solver deliberately does not search future barriers — that would put
        the wall set in the state and make the space exponential — so on its own
        it answers a question about a board that stops changing. It does not.
        A live sub-game found the gap exactly: our thief sat in the corner (6,6)
        with twelve plies of proven safety, the officer spent one barrier, and
        safety fell to one and then to zero. Proven safe, then captured.

        So the officer is allowed its cheapest reply here: a wall on any cell it
        could reach. Sealing the cell we are standing on is a capture outright
        under rule 46, which is why that case returns zero without solving — and
        why the old "never finish adjacent to the officer" veto falls out of this
        as a consequence rather than having to be asserted separately.
        """
        board, barriers = context.state.board, context.state.barriers
        base = table.plies_after_move(target, officer)
        walls_left = max(0, context.barriers_max - len(barriers))
        if not walls_left or not base:
            return base
        if target == officer or target in board.neighbors(officer, barriers):
            return 0
        worst = base
        for wall in self._buildable(board, officer, barriers):
            built = self._table(context, frozenset(barriers | {wall}))
            worst = min(worst, built.plies_after_move(target, officer))
        return worst

    @staticmethod
    def _buildable(board, officer: Cell, barriers) -> set:
        """The cells the officer could wall this turn.

        This is one ply of barrier lookahead and it is knowingly not enough. A
        determined officer's real threat is move-then-build: in one measured
        sub-game our thief sat in the corner (6,6) reading twelve plies of safety
        even after allowing for every wall the officer could raise from where it
        stood, and the officer then stepped sideways and walled (5,6) from there,
        turning the corner into a one-exit cell. Twelve, one, zero.

        Searching that second ply was tried and is not worth it: it costs about
        twenty solves a turn instead of four and, measured over 300 sub-games,
        changed no outcome at all — the pinch it was meant to catch was already
        decided several moves earlier, by the choice to be in the corner. That
        conclusion still holds. The response to it did not: prevention was left
        to ``mobility_weight`` in the inherited positional score, which only ever
        breaks ties *among moves of equal safety*, so it could never outvote the
        distance that draws a thief to a corner in the first place. Room is now
        ranked inside :meth:`_safety` where it can actually fire.

        So the residual is real and worth stating plainly: against an officer
        that spends walls to pinch a corner, this thief is not provably safe.

        This paragraph used to end "in the fixed arena that is roughly one
        sub-game in three hundred". Live, against an officer that actually
        pinches, it was three sub-games in three — every thief window of the
        counted series against imreeyal, same corner, same two walls, same
        rule-47 concession. The 1-in-300 came from an arena whose only officer
        never spent a wall on a corner, so it was measuring our own blind spot
        with our own blind instrument. Do not trust that number again until
        ``scripts/arena.py`` has a pinching officer in its opponent set.
        """
        return set(board.neighbors(officer, barriers))

    def _table(self, context, barriers: frozenset):
        """Solve for a barrier set, once per turn however often it is asked for."""
        if barriers not in self._solved:
            self._solved[barriers] = pursuit.solve(
                context.state.board,
                barriers,
                self._horizon(context),
                stay_allowed=context.state.can_stay,
            )
        return self._solved[barriers]

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
