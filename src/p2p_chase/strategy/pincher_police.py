"""``PincherPolice`` — the officer that beat us, rebuilt from its own evidence.

imreeyal won a counted series against us 30-90 with a tactic our officer does
not possess. In all three of their winning windows they spent **two** barriers
out of fourteen: one to take our thief's corner from two exits to one, a second
to take it to zero, and rule 47 did the rest. Our own officer, over the same
three windows, placed **zero of fourteen**.

The reason is a gate. :meth:`ArchitectPolice._wall` scores a wall structurally --
cut vertices, expected region shrink -- and spends only when that value clears
``wall_threshold``. A thief keeping its distance never lets belief concentrate on
a cell adjacent to us, so the value never clears, and the planner ends up firing
only when we are already winning. It is the precise inverse of what is needed.

This class changes one judgement and inherits everything else. A wall that
reduces the *exits* of the cell we believe the thief occupies is worth building
on its own account, whatever its structural score. Exits are what the thief now
defends in :meth:`SafeThief._safety`, so both sides of our codebase reason about
one quantity, and a corner is finally expensive for the thief precisely because
it is cheap for the officer.

Written to be honest about what it is: a **reproduction** of an opponent's tactic
inferred from six signed sub-games, not their code. It is the instrument the
arena was missing -- without an officer that pinches, our benchmark certified
this failure at one sub-game in three hundred while the live rate was three in
three -- and, if it earns it on the numbers, a candidate for our own officer.
"""

from p2p_chase.constants import Cell, Role
from p2p_chase.strategy import barriers as barrier_planner
from p2p_chase.strategy.base import TurnContext
from p2p_chase.strategy.police_brain import ArchitectPolice

#: Exits at or below which a cell counts as pinchable. Three is deliberate
#: rather than two: waiting for two means the thief is already in the corner and
#: has had a turn to leave it, and the cell we can still cheaply cage is the one
#: it is about to enter.
_PINCH_EXITS = 3

#: Belief mass needed on a cell before we spend a wall shrinking it. Well below
#: ``seal_confidence`` (0.5), because sealing the thief's own cell is an outright
#: capture claim and must be near-certain, while narrowing its room is cheap and
#: stays useful even when we are only roughly right about where it is.
_PINCH_CONFIDENCE = 0.12


class PincherPolice(ArchitectPolice):
    """Pursuit that spends walls on the thief's room, not on board structure."""

    role = Role.POLICE

    def _wall(self, context: TurnContext, belief_cells: list[tuple[Cell, float]]):
        """Build to shrink the thief's escape room, else fall back to structure.

        The inherited planner is not replaced, it is given a second reason to
        fire. Where a legal wall reduces the exits of a cell we credibly believe
        the thief is on, we take it without consulting ``wall_threshold``; where
        no such wall exists we defer to ``ArchitectPolice`` unchanged, so nothing
        this class does can make the officer build *less* than it used to.
        """
        pinch = self._pinch(context, belief_cells)
        return pinch if pinch is not None else super()._wall(context, belief_cells)

    def _pinch(self, context: TurnContext, belief_cells: list[tuple[Cell, float]]):
        """The cheapest wall that takes room away from the believed thief."""
        state = context.state
        if max(0, context.barriers_max - state.my_barriers) <= self._reserve():
            return None
        quarry = self._quarry(context, belief_cells)
        if quarry is None:
            return None
        board, walls = state.board, state.barriers
        exits = board.neighbors(quarry, walls)
        if len(exits) > _PINCH_EXITS:
            return None
        # Only cells we could legally build on this turn, and only those that are
        # actually one of the quarry's exits -- a wall anywhere else may look
        # structurally attractive without narrowing the cage at all.
        for direction, cell in board.legal_moves(state.position, walls):
            if cell not in exits or cell == quarry:
                continue
            plan = self._plan_for(context, direction, cell, belief_cells)
            if plan is not None and plan.viable:
                return plan
        return None

    def _quarry(self, context: TurnContext, belief_cells) -> Cell | None:
        """The cell we are willing to spend a wall narrowing, if any."""
        if not belief_cells:
            return None
        cell, mass = max(belief_cells, key=lambda item: item[1])
        return cell if mass >= self._tune("pinch_confidence", _PINCH_CONFIDENCE) else None

    def _plan_for(self, context: TurnContext, direction, cell: Cell, belief_cells):
        """Score one specific wall through the shared planner.

        Routed through :func:`barriers.evaluate_wall` rather than hand-rolled so
        the safety checks it already performs -- most importantly
        ``own_region_floor``, which stops the officer walling itself into a
        pocket, and the rule that a wall must never *enlarge* the thief's
        expected region -- apply to a pinch exactly as they do to a structural
        wall. Only the *reason* for building differs, never the vetoes.
        """
        state = context.state
        return barrier_planner.evaluate_wall(
            state.board, state.position, state.barriers, belief_cells, direction, cell,
            anchor_bonus=self._tune("anchor_bonus", 1.2),
            cut_bonus=self._tune("cut_bonus", 6.0),
            occupancy_bonus=self._tune("occupancy_bonus", 12.0),
            own_region_floor=self._tune("own_region_floor", 0.25),
        )

    def _reserve(self) -> int:
        """Walls held back so the endgame squeeze is never spent early."""
        return int(self._tune("barrier_reserve", 3))
