"""Reference-style baseline brains, used as a measuring stick.

These reproduce the *policy* described in the course's reference simulator — a
thief that maximises Manhattan distance from the belief peak, and an officer that
minimises it while dropping a wall at random every so often. They are here for
one reason: to give the research report a fair, fixed opponent to measure our
strategies against, so a claim like "the architect officer captures more" is a
number rather than an opinion.

They are never selected for league play. Nothing outside ``scripts/arena.py``
and the test suite constructs them.
"""

from p2p_chase.constants import Direction, MoveType, Role
from p2p_chase.strategy.base import BrainBase, TurnContext


class GreedyThief(BrainBase):
    """Runs directly away from the single most likely officer cell."""

    role = Role.THIEF

    def _pick_move(self, moves: list[tuple[Direction, tuple]], context: TurnContext):
        threat = context.belief.most_likely()
        board = context.state.board
        return max(
            moves,
            key=lambda move: (
                board.distance(move[1], threat),
                move[1] not in context.state.visited,
            ),
        )


class GreedyPolice(BrainBase):
    """Walks at the belief peak and sometimes walls the cell it would step onto."""

    role = Role.POLICE
    barrier_chance = 0.15

    def _decide_move(self, context: TurnContext):
        state = context.state
        moves = state.board.legal_moves(state.position, state.barriers)
        if not moves:
            return MoveType.HOLD, None, None, "boxed in", False
        direction, target = self._pick_move(moves, context)
        if state.my_barriers < context.barriers_max and self._rng.random() < self.barrier_chance:
            return MoveType.BARRIER, direction, target, "random wall", False
        # The reference claims a capture on every single move, which broadcasts
        # its exact cell each turn. Reproduced faithfully — it is precisely the
        # behaviour our thief is built to punish.
        return MoveType.MOVE, direction, target, "greedy approach", True

    def _pick_move(self, moves: list[tuple[Direction, tuple]], context: TurnContext):
        target_cell = context.belief.most_likely()
        board = context.state.board
        return min(moves, key=lambda move: (board.distance(move[1], target_cell), move[1]))
