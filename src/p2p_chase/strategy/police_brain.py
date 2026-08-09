"""``ArchitectPolice`` — pursue by shrinking the board, not by chasing the peak.

Chasing ``argmax b(s)`` is the obvious officer and it loses. The belief peak
jitters from turn to turn as scent readings arrive, so a peak-chaser oscillates,
and on an open board a thief that simply keeps its distance survives all
thirty-five steps without ever being threatened.

This officer optimises two things at once, which is what the barrier power is
for:

* **Pressure** — belief-weighted *expected* walking distance to the thief, over
  the real barrier graph. Minimising an expectation is stable where chasing a
  single argmax is not.
* **Containment** — the thief's expected remaining room. Walls make this fall
  monotonically, and once it falls far enough capture stops being luck.

Capture is claimed whenever the officer's action lands on a cell the thief may
occupy — by stepping onto it, or by *sealing* it, which the book counts as a
capture in its own right (mandatory rule 46).
"""

from p2p_chase.constants import Cell, Direction, MoveType, Role
from p2p_chase.strategy import barriers as barrier_planner
from p2p_chase.strategy import reachability
from p2p_chase.strategy.base import BrainBase, TurnContext

#: Belief mass on one adjacent cell above which we commit to a capture claim.
_CAPTURE_CONFIDENCE = 0.18
#: How many of the hottest cells to reason over. The tail is noise and costs time.
_BELIEF_CELLS = 16


class ArchitectPolice(BrainBase):
    """Pursuit as spatial engineering."""

    role = Role.POLICE

    def _decide_move(self, context: TurnContext):
        state = context.state
        moves = state.board.legal_moves(state.position, state.barriers)
        belief_cells = context.belief.top_cells(_BELIEF_CELLS)

        seal = self._adjacent_seal(moves, context)
        if seal is not None:
            direction, cell = seal
            return (
                MoveType.BARRIER, direction, cell,
                f"seal {cell}: the thief is standing there and cannot move first", True,
            )

        strike = self._capture_shot(moves, context)
        if strike is not None:
            direction, target = strike
            return (
                MoveType.MOVE, direction, target,
                "capture claim on the hottest adjacent cell", True,
            )

        plan = self._wall(context, belief_cells)
        if plan is not None:
            # Sealing the cell the thief occupies *is* a capture (rule 46), so a
            # wall on a cell we think is occupied is claimed as one.
            claims = context.belief.probability(plan.cell) >= self._tune(
                "barrier_claim_confidence", 0.10
            )
            return MoveType.BARRIER, plan.direction, plan.cell, plan.rationale, claims

        if not moves:
            return MoveType.HOLD, None, None, "boxed in; holding position", False
        direction, target = self._pick_move(moves, context)
        # Deliberately silent: a capture claim announces our exact cell, and the
        # reference implementation makes one every single turn. We claim only
        # when we mean it, so an opponent cannot triangulate us for free.
        return (
            MoveType.MOVE, direction, target,
            self._explain(context, target, belief_cells), False,
        )

    def _adjacent_seal(
        self, moves: list[tuple[Direction, Cell]], context: TurnContext
    ) -> tuple[Direction, Cell] | None:
        """Wall the cell the thief is standing on, when we are sure it is standing there.

        This is the one capture the thief cannot answer. Stepping onto its square
        is a claim it gets to move away from next turn; sealing the square is a
        capture by rule 46 the moment the wall goes up, and the thief has already
        spent its move. It costs a barrier and a turn, which is nothing against
        ending the sub-game.

        It was previously unreachable. ``_capture_shot`` only ever considered
        *stepping*, and the seal could only be found through the barrier planner,
        whose spend rule declines to build whenever the thief is far away — and so
        also declined to notice it was standing next to us.
        """
        if context.state.my_barriers >= context.barriers_max:
            return None
        target = context.belief.most_likely()
        if context.belief.probability(target) < self._tune("seal_confidence", 0.5):
            return None
        for direction, cell in moves:
            if cell == target:
                return direction, cell
        return None

    def _capture_shot(
        self, moves: list[tuple[Direction, Cell]], context: TurnContext
    ) -> tuple[Direction, Cell] | None:
        """Step onto an adjacent cell we believe strongly enough is occupied."""
        if not moves:
            return None
        direction, target = max(moves, key=lambda m: (context.belief.probability(m[1]), m[1]))
        threshold = self._tune("capture_confidence", _CAPTURE_CONFIDENCE)
        return (direction, target) if context.belief.probability(target) >= threshold else None

    def _wall(self, context: TurnContext, belief_cells: list[tuple[Cell, float]]):
        """Decide whether to forgo movement and build."""
        state = context.state
        left = max(0, context.barriers_max - state.my_barriers)
        if left <= 0:
            return None
        plan = barrier_planner.plan_barrier(
            state.board, state.position, state.barriers, belief_cells,
            anchor_bonus=self._tune("anchor_bonus", 1.2),
            cut_bonus=self._tune("cut_bonus", 6.0),
            occupancy_bonus=self._tune("occupancy_bonus", 12.0),
            own_region_floor=self._tune("own_region_floor", 0.25),
        )
        if plan is None:
            return None
        distances = reachability.distance_map(state.board, state.position, state.barriers)
        spend = barrier_planner.should_spend(
            plan=plan,
            barriers_left=left,
            steps_remaining=context.steps_remaining,
            total_steps=max(1, context.state.step_number + max(1, context.steps_remaining)),
            expected_distance=reachability.expected_distance(
                distances, belief_cells, state.board.cells
            ),
            board_size=state.board.size,
            reserve=int(self._tune("barrier_reserve", 3)),
            threshold=self._tune("wall_threshold", 2.5),
        )
        return plan if spend else None

    def _pick_move(self, moves: list[tuple[Direction, Cell]], context: TurnContext):
        belief_cells = context.belief.top_cells(_BELIEF_CELLS)
        scored = [
            (self._score(target, context, belief_cells), direction, target)
            for direction, target in moves
        ]
        scored.sort(key=lambda item: (-item[0], item[2]))
        _, direction, target = scored[0]
        return direction, target

    def _score(
        self, cell: Cell, context: TurnContext, belief_cells: list[tuple[Cell, float]]
    ) -> float:
        """Value of standing on ``cell`` next turn. Higher is better for the officer."""
        board = context.state.board
        barriers = context.state.barriers
        far = board.cells

        distances = reachability.distance_map(board, cell, barriers)
        pressure = reachability.expected_distance(distances, belief_cells, far)
        containment = reachability.expected_region_size(board, belief_cells, barriers | {cell})
        coverage = context.belief.mass_within(cell, 1)
        # How much room the thief has left once we are standing here. Distance
        # alone is a chase an informed evader wins forever on an open board: it
        # simply keeps two cells between us and we oscillate until the clock runs
        # out. Squeezing is the officer's actual job -- take away the places it can
        # be in a few moves, drive it onto the rim where the board itself becomes
        # the far wall, and only then is there anything worth sealing.
        squeeze = self._thief_room(board, barriers | {cell}, belief_cells)
        # Sitting still while the clock runs out is a loss for us, so mild bias
        # toward the centre of mass keeps the officer engaged on quiet turns.
        centrality = 1.0 - board.distance(cell, context.belief.most_likely()) / (2 * board.size)

        return (
            -self._tune("pressure_weight", 1.0) * (pressure / max(1, board.size))
            - self._tune("containment_weight", 0.5) * (containment / board.cells)
            - self._tune("squeeze_weight", 1.4) * squeeze
            + self._tune("coverage_weight", 1.2) * coverage
            + self._tune("centrality_weight", 0.2) * centrality
        )

    @staticmethod
    def _thief_room(board, obstacles, belief_cells: list[tuple[Cell, float]]) -> float:
        """Belief-weighted local freedom left to the thief, in [0, 1].

        Deliberately the same measure the thief maximises for itself, so the two
        agents are playing tug-of-war over one number instead of optimising past
        each other.
        """
        total = weight = 0.0
        for cell, probability in belief_cells:
            if probability <= 0.0 or cell in obstacles:
                continue
            total += probability * reachability.mobility(board, cell, obstacles)
            weight += probability
        return total / weight if weight else 1.0

    def _explain(
        self, context: TurnContext, cell: Cell, belief_cells: list[tuple[Cell, float]]
    ) -> str:
        board = context.state.board
        distances = reachability.distance_map(board, cell, context.state.barriers)
        return (
            f"pressure={reachability.expected_distance(distances, belief_cells, board.cells):.2f} "
            f"containment={reachability.expected_region_size(board, belief_cells, context.state.barriers | {cell}):.1f} "
            f"walls_left={max(0, context.barriers_max - context.state.my_barriers)}"
        )
