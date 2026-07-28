# Strategy guide — writing your own brain

The move policy is the graded seam. Everything else in this repository exists to
let you swap it out in one line of configuration and measure whether the swap
helped.

## The contract

```python
from p2p_chase.strategy.base import BrainBase, TurnContext
from p2p_chase.constants import Direction, MoveType, Role


class MyThief(BrainBase):
    role = Role.THIEF

    def _pick_move(self, moves: list[tuple[Direction, tuple]], context: TurnContext):
        """Return one (direction, target) from `moves`. Pure Python, always."""
        threat = context.belief.most_likely()
        return max(moves, key=lambda move: context.state.board.distance(move[1], threat))
```

Point at it in `config/<role>/game.toml` and it plays:

```toml
[strategy]
thief_class = "my_package.brains:MyThief"
```

Override `_pick_move` for a movement heuristic. Override `_decide_move` when you
need the full action space — barriers, deliberate capture claims, conceding an
enclosure. It returns a five-tuple:

```python
(move_type, direction, target_cell, rationale, claims_capture)
```

`rationale` is sealed into the audit log, so write something you would be happy
to have read back to you. `claims_capture` is discussed below and matters more
than it looks.

## What the brain may see

`TurnContext` is assembled explicitly rather than handing you the runtime, so a
strategy *cannot* accidentally consult the opponent's private state — there is no
path from here to it.

| Field | What it is |
|---|---|
| `state` | My position, my visited set, every barrier I know about, my quota |
| `belief` | `b(s)` over the opponent's cell — the closest thing to seeing them |
| `trust` | Beta-Bernoulli estimate of how honest this opponent has been |
| `opponent_hint` | Their last sentence, raw |
| `barriers_max`, `steps_remaining` | The budgets you are spending against |
| `tuning` | Your `[strategy.police]` / `[strategy.thief]` block |

## Tools worth using

`p2p_chase.strategy.reachability` is where the useful spatial questions live.
The single most important lesson we learned: **Manhattan distance is wrong the
moment the first barrier goes up.** Two cells one apart on the grid can be twenty
apart on the graph.

| Function | Answers |
|---|---|
| `distance_map(board, origin, barriers)` | True step distance to every reachable cell |
| `region_size(board, origin, barriers)` | How much room a cell still has — the thief's whole objective |
| `expected_region_size(board, belief_cells, barriers)` | The same, belief-weighted, for the officer |
| `expected_distance(distances, belief_cells, unreachable)` | Expected time-to-catch; stable where `argmax` jitters |
| `is_cut_vertex(board, cell, barriers)` | Would sealing this cell sever a corridor? |
| `exits(board, cell, barriers)` | Degree. One means a dead end, and one wall from losing |

## Five things we learned the hard way

**1. Do not chase the belief peak.** It jitters as scent arrives, so a peak-chaser
oscillates. Minimise *expected* distance instead.

**2. Room beats distance for the thief.** The losing pattern is always a thief
that maximises distance and walks into a far corner that then gets sealed. Weight
region size above separation.

**3. Price walls structurally.** On an open board a wall removes exactly one cell,
so any planner that prices walls by immediate gain builds nothing at all — ours
captured 0 % until we fixed this. Value anchoring against existing walls and
edges, cut vertices, and the probability the cell is occupied.

**4. A capture claim announces your exact position.** It can only name the cell you
just stepped onto. The reference implementation claims on *every* move, handing
the thief a free position fix each turn; our officer claims only when it means it,
and our thief calls `belief.collapse_to()` on opponents who leak. Set
`claims_capture=True` deliberately.

**5. Standing still is loud.** Scent merges by maximum and decays multiplicatively,
so a stationary agent builds a bright, unambiguous beacon. `context.state.board`
plus `SmellField.emission()` will tell you how loudly a candidate cell would
shout before you commit to it.

## Talking

The hint layer is separate and never decides the move (mandatory rule 25).
Configure it independently:

```toml
[trash_talk]
provider      = "template"   # 0 tokens, no network, the default
every_n_steps = 1
lie_rate      = 0.45
```

If you write your own talker, implement `say(role, context, target)` returning
`(hint, intent, reasoning, prompt)`. Two rules that are not optional: the hint
must be free natural language with no coordinates (rule 27), and `intent` must be
the honest truth about whether you are lying — it is committed *before* the hint
is revealed, so a false flag is exposed at the audit (rule 22).

Worth reading before designing a bluffing policy:
[`strategy/talk/bluff.py`](../src/p2p_chase/strategy/talk/bluff.py). Lying at a
fixed rate is trivially beaten, because your own scent contradicts every claim
and an opponent who knows you always lie simply inverts you. We treat credibility
as a balance that is spent and rebuilt.

## Measuring a change

Never ship a strategy change on a hunch — we nearly shipped a benchmark that was
one match repeated thirty times.

```bash
uv run python scripts/arena.py --matches 60 --cop architect --thief greedythief
```

```bash
uv run python scripts/arena.py --matches 60 --cop-tune '{"wall_threshold": 2.2}'
```

Register a new brain in `BRAINS` in `scripts/arena.py` to benchmark it. Always
run against **both** archetypes: a change that helps against a naive opponent and
collapses against a strong one is not an improvement, it is overfitting.
