"""``OpenSpaceThief`` — survive by never running out of room.

Survival pays 10 and capture still pays 5, so the thief is not playing for a
draw: it is playing for time. Thirty-five steps is a long while on a 7x7 board
that the officer is actively bricking up, and the losing pattern is always the
same — a thief that maximises *distance* walks itself into a corner that is far
away and sealed.

So distance is only one term of three, and not the largest:

* **Room** — the size of the connected region the candidate cell belongs to,
  computed over the real barrier set. This dominates: a cell two steps from the
  officer with the whole board behind it beats a cul-de-sac six steps away.
* **Separation** — true graph distance to the believed officer, not Manhattan,
  because walls change who is actually near whom.
* **Novelty** — a light preference for cells not recently visited. Re-treading
  ground both re-deposits scent where the officer is already looking and tends
  to produce the oscillation that lets a pursuer close in.
"""

from p2p_chase.constants import Cell, Direction, MoveType, Role
from p2p_chase.strategy import reachability
from p2p_chase.strategy.base import BrainBase, TurnContext

#: How far ahead the officer is assumed to project when we judge a cell's safety.
_THREAT_HORIZON = 2

#: How far ahead we measure our own escape room. Three moves is the shortest
#: window in which a pursuer can turn "few ways out" into "none".
_ESCAPE_HORIZON = 3


class OpenSpaceThief(BrainBase):
    """Evasion by region maximisation under a Bayesian threat model."""

    role = Role.THIEF

    def _decide_move(self, context: TurnContext):
        state = context.state
        moves = state.board.legal_moves(state.position, state.barriers)
        if not moves:
            # Sealed in. The book counts this as a capture and we must say so:
            # denying it would be exposed at the audit and forfeit the match.
            return MoveType.HOLD, None, state.position, "sealed in with no legal move", False
        direction, target = self._pick_move(moves, context)
        return MoveType.MOVE, direction, target, self._explain(context, target), False

    def _pick_move(self, moves: list[tuple[Direction, Cell]], context: TurnContext):
        scored = [(self._score(target, context), direction, target) for direction, target in moves]
        scored.sort(key=lambda item: (-item[0], item[2]))  # deterministic tie-break
        _, direction, target = scored[0]
        return direction, target

    def _score(self, cell: Cell, context: TurnContext) -> float:
        """Value of standing on ``cell`` after this move. Higher is safer."""
        state = context.state
        board = state.board
        threat = context.belief.most_likely()

        # The officer occupies a cell, so treat it as blocked when measuring room.
        obstacles = state.barriers | {threat}
        room = reachability.region_size(board, cell, obstacles) if cell != threat else 0
        room_ratio = room / board.cells

        distances = reachability.distance_map(board, cell, state.barriers)
        separation = distances.get(threat, board.cells)
        separation_ratio = min(1.0, separation / max(1, board.size))

        # Local freedom. Region size cannot see a corner — it reports 48/49 there
        # just as it does in the middle — so without this the thief trades room it
        # cannot measure for distance it can, and reaches the far corner with an
        # excellent score and nowhere to go.
        room_nearby = reachability.mobility(board, cell, obstacles, _ESCAPE_HORIZON)

        novelty = 0.0 if cell in state.visited else 1.0
        ways_out = reachability.exits(board, cell, state.barriers)
        # A dead end is not merely cramped, it is terminal: one barrier ends the game.
        deadend_penalty = 1.0 if ways_out <= 1 else 0.0
        # Standing where the officer could arrive next turn is worth avoiding outright.
        contact = 1.0 if separation <= 1 else 0.0
        exposure = context.belief.mass_within(cell, _THREAT_HORIZON)

        return (
            self._tune("region_weight", 1.0) * room_ratio
            + self._tune("mobility_weight", 1.1) * room_nearby
            + self._tune("distance_weight", 0.35) * separation_ratio
            + self._tune("novelty_weight", 0.15) * novelty
            - self._tune("deadend_penalty", 0.8) * deadend_penalty
            - self._tune("contact_penalty", 1.5) * contact
            - self._tune("exposure_weight", 0.4) * exposure
        )

    def _explain(self, context: TurnContext, cell: Cell) -> str:
        state = context.state
        threat = context.belief.most_likely()
        room = reachability.region_size(state.board, cell, state.barriers | {threat})
        distances = reachability.distance_map(state.board, cell, state.barriers)
        return (
            f"room={room}/{state.board.cells} "
            f"gap={distances.get(threat, -1)} "
            f"exits={reachability.exits(state.board, cell, state.barriers)}"
        )
