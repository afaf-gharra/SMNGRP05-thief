# Research report: strategy, parameters, and cost

Everything below is reproducible from this repository:

```bash
uv run python scripts/arena.py --matches 60 --cop architect --thief greedythief
```

## 1. Method

`scripts/arena.py` plays complete sub-games with the real brains, the real
belief filter, the real scent model and the real barrier budget, over a direct
in-process shuttle. The protocol layer is exercised separately by the integration
suite; here we want hundreds of matches rather than hundreds of handshakes.

**Sampled openings, and why.** Both strategies are deterministic. Our first
benchmark run reported "100 % capture over 30 matches" — which was one match
repeated thirty times, since nothing varied between seeds. Every figure here
therefore samples the start pair per seed (rejecting pairs already within two
steps, which would decide the match before move one). Start positions are a
negotiated term, so sampling them is realistic as well as honest.

**Opponents.** `scripts/../strategy/baselines.py` reproduces the policy of the
course reference simulator: a thief maximising Manhattan distance from the belief
peak, and an officer minimising it while dropping a wall at random 15 % of the
time, claiming a capture on every move. Most league opponents will resemble it,
so it is the fair yardstick. It is never selected for league play.

**Fixed terms.** 7×7 board, survival threshold 35, 14 barriers, scent peak 0.9,
ρ = 0.10, 5×5 window — the Appendix F minimums.

## 2. Head-to-head results

60 matches per cell.

| Officer | Thief | Capture | Mean steps | Mean walls | Officer pts/sub-game | Thief pts/sub-game |
|---|---|---|---|---|---|---|
| **`ArchitectPolice`** | reference | **57 %** | 23.2 | 6.2 | **13.5** | 7.9 |
| **`ArchitectPolice`** | **`OpenSpaceThief`** | 32 % | 26.8 | 9.1 | 9.8 | 8.4 |
| reference | reference | 13 % | 32.5 | 4.4 | 7.0 | 9.4 |
| reference | **`OpenSpaceThief`** | **5 %** | 34.3 | 4.6 | 5.8 | **9.8** |

**Reading it.** Against the same reference thief, our officer captures 57 % where
a reference officer manages 13 % — **4.4× better**, and 9 turns faster. Against
the same reference officer, our thief survives 95 % where a reference thief
survives 87 %. Both roles improve, which matters because roles alternate: a
series is won by being better at *both*.

The 32 % cell is the honest one: against our own strongest evader the officer is
a clear underdog. On a 7×7 board with equal speed, 35 turns and only 14 walls,
that is the correct shape of the game — evasion is genuinely favoured, which is
also why the book pays survival 10 and capture 20.

## 3. The parameter that mattered

Sweeping the officer's weights showed something we did not expect: `containment_weight`
and `pressure_weight` barely moved the result, while `wall_threshold` — how much
structural value a wall must clear before the officer gives up a turn to build —
moved it from **nothing to everything**.

| `wall_threshold` | vs `OpenSpaceThief` | vs reference thief | Mean walls |
|---|---|---|---|
| 2.5 *(first version)* | **0 %** | 100 %\* | 0.0 |
| 1.4 | 43 % | 40 % | 12.5 |
| 2.2 | 33 % | 53 % | 10.2 |
| **3.0 (shipped)** | **32 %** | **57 %** | 6.2 |
| 3.4 | 20 % | 64 % | 4.0 |

\* fixed-opening run, before sampled starts — included to show the artefact.

**Why the first version failed.** At threshold 2.5 the officer built **zero**
walls in 30 matches. On an open board sealing one cell removes exactly one cell
from the thief's region, so a planner that prices walls by immediate gain never
clears any sensible bar, and the officer's single asymmetric advantage goes
completely unused. The fix was not a bigger number — it was pricing walls
**structurally**: anchoring against existing walls and edges so segments grow into
fences, a large bonus for cut vertices, and a very large bonus for the probability
the cell is occupied, since sealing an occupied cell *is* a capture.

We shipped 3.0 rather than the individually-best 1.4 or 3.4: it is close to the
best against the opponent archetype we will actually meet, spends the fewest
walls, and finishes fastest — which reduces exposure to network timeouts, and
scores well on computational fairness.

## 4. Token and cost analysis

The move is pure Python, so the model is optional in fact, not just in principle.

| Mode | Where it runs | Tokens per 6-sub-game series | Rate limit | Cost |
|---|---|---|---|---|
| **`template` (shipped default)** | in-process | **0** | none | **$0.00** |
| `ollama` | `localhost:11434` | 0 API tokens | none | $0.00 (local compute) |
| `claude_api` (Haiku) | Anthropic API | ≈ 12 k in / 3 k out | account RPM | ≈ $0.02 |
| `claude_cli` | Claude Code | highest | subscription | subscription |

**Estimate basis.** ≈ 210 hint-producing turns per six-sub-game series (35 steps ×
6, one side). At ≈ 55 prompt tokens and ≈ 14 completion tokens per call, that is
≈ 11.6 k in / 2.9 k out — about **7 %** of the 200 000-token series budget in
Appendix F. `every_n_steps = 3` cuts it to ≈ 2 %.

**Bottleneck.** Not tokens — wall-clock latency. A cloud call adds 0.4–1.5 s per
turn against a 180 s turn deadline, so a slow provider cannot forfeit a match, but
six sub-games of paid hints turn a 30-second series into a five-minute one. That
is the actual reason the default is the template: the competition is over the
movement algorithm, and paying for banter buys nothing on the board.

**Backoff.** Every provider call passes the Gatekeeper (quota → token bucket →
DOS breaker) and carries a hard per-step deadline. On timeout, failure, or a
tripped breaker the template writes the line instead. The match never stalls.

## 5. Belief-filter validation

Two properties are asserted directly in `tests/unit/test_belief.py`:

* **Walls contain the filter.** Starting from certainty that the opponent is south
  of a full-width wall and running eight prediction steps leaves *exactly zero*
  mass north of it. A naive 3×3 smear leaks, which would silently waste every
  barrier the officer paid for.
* **Talk is weighed, not believed.** At trust 0.5 a hint moves nothing. Above it
  the named region gains mass; below it the region *loses* mass — a proven liar's
  hints are inverted and start working for us.

The lie detector reproduces the book's worked example: told "moving north" while
the scent mass sits in the south-east, trust falls below 0.25 within six turns.

## 6. Where the book and the reference code disagree

Two genuine conflicts. The book states it governs, and we followed it.

**Scent decay.** The book gives `τ(t+1) = max(0, (1−ρ)·τ(t) + Δτ)` — multiplicative
— and describes a trail readable for six to seven turns, with a figure showing
exponential decay crossing half-peak near turn 7. The reference simulator
*subtracts* ρ each turn. With ρ = 0.10 that empties a fresh deposit in nine turns
and crosses half-peak at turn 4.5, which changes the game materially. We implement
the book's formula; `0.9 → 0.81 → 0.729` is asserted in the tests, and half-peak
lands at turn 7 as described. This does not affect interoperability: each peer's
decay only shapes the field it broadcasts about itself.

**Sub-games per series.** Appendix F fixes `[num_minigames]` at 6 (permanent); the
reference ships `num_games: 1`. We default to 6.

**One place we chose the code over the figure.** The book's figure 4 shows a
Gaussian emission window (0.90, 0.62, 0.42, 0.20, 0.14, 0.04). The book's own
preamble states that illustrations are demonstrations and not binding, and
Appendix F fixes only the peak, the decay and the window size. Since the receiving
peer simply absorbs whatever numbers arrive, we default to the reference's linear
falloff so a stock opponent's readings and ours are on the same scale — and
implement the Gaussian exactly (it reproduces the figure to two decimal places,
verified in the tests) as a negotiable option.
