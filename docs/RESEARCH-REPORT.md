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

> **Correction (17 Aug).** Every figure originally published in this section was
> measured on a harness that did not play the same game as the live peer. The
> arena fed the belief filter the blunt `observe_smell` weighting instead of the
> sharpened peak decode the peer actually runs, and it revealed the officer's
> cell to the thief only when `claims_capture` was set, whereas the live officer
> declares its square every turn. Both errors flattered the officer. The
> headline claim — 32 % capture against our own thief — did not survive contact:
> the live result against uoh-ay26 was **0 captures in 3 sub-games**. The table
> below is a re-measurement after `scripts/arena.py` was corrected to mirror
> `peer/turn_handler`, and it reproduces the live result.

60 matches per cell, corrected harness.

| Officer | Thief | Capture | Mean steps | Mean walls | Officer pts | Thief pts |
|---|---|---|---|---|---|---|
| **`ArchitectPolice`** | baseline `GreedyThief` | **28 %** | 32.1 | 1.8 | 9.2 | 8.6 |
| **`ArchitectPolice`** | `OpenSpaceThief` (old) | **0 %** | 35.0 | 1.8 | 5.0 | 10.0 |
| **`ArchitectPolice`** | **`SafeThief`** | **0 %** | 35.0 | 0.0 | 5.0 | **10.0** |
| baseline `GreedyPolice` | baseline `GreedyThief` | 5 % | 34.6 | 4.8 | 5.8 | 9.8 |
| baseline `GreedyPolice` | **`SafeThief`** | **0.7 %** | 34.9 | 4.9 | 5.2 | **9.9** |

**Reading it honestly.** Our officer beats the baseline officer against the same
weak thief (28 % against 5 %), and is a clear underdog against any competent
evader — 0 % against both of ours. That is the true shape of the game and it
matches theory: with equal speed and STAY available on an open board, capture
cannot be forced, which is why the book pays survival 10 and capture 20.

The thief numbers understate the change, because both thieves survive everything
our own officer can do. The improvement is visible only where it matters — in
positions a good pursuer can reach. Sweeping 4000 random boards finds **53**
where `OpenSpaceThief` is captured immediately and `SafeThief` survives
indefinitely, all of them diagonal contact where every *step* is covered and only
standing still is safe. `OpenSpaceThief` was never offered standing still.

**The residual, stated plainly.** `SafeThief` is captured in roughly 1 sub-game
in 300 by a wall-building officer. The solver does not search future barriers —
that would put the wall set in the state and make the space exponential — so a
patient officer can move-then-build to pinch a corner the thief entered while it
still read as safe. One ply of barrier lookahead is applied and closes the
one-move version; searching the second ply was measured and changed no outcome,
because by then the position was already decided. This is a genuine limit, not a
rounding error.

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

> **Correction (17 Aug).** This sweep was run on the same uncorrected harness as
> the table in §2, so the absolute percentages here are not trustworthy either.
> The *finding* — that `wall_threshold` dominates the officer's other weights —
> was reproduced qualitatively after the fix and is why the officer still ships
> at 3.0, but these specific numbers should be read as a record of what was
> measured, not as a claim about the game.

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
and crosses half-peak at turn 4.5, which changes the game materially.

Both are implemented and selectable by `smell.decay_mode`. **What we ship, and
what we declare to opponents, is the subtractive mode** — `subtractive_chebyshev_v1`,
the league kit's core model, which is what every team we have met actually plays.
An earlier revision of this section claimed we shipped the book's multiplicative
form; that was true of the code path, not of the default, and the discrepancy is
corrected here rather than left to be found in the source.

The choice is interoperability, not a judgement that the book is wrong. The decay
mode is **not one of the fourteen signed terms**, so two peers can agree every hash
and still fade their fields differently — the worst shape a disagreement can take,
because the match plays out cleanly and only the audits disagree, with nothing to
point at. That is why the mode is declared in writing as a named model with a
worked example, and why we keep declaring ours even against a peer who declines to
declare theirs.

The divergence is real and measurable. A 0.9 deposit under our subtractive mode
reads 0.20 at turn 7 and is gone by turn 9; under the book's multiplicative mode it
reads 0.43 at turn 7 and still 0.31 at turn 10. Played against a multiplicative
peer (anrbj666, 24/08), their field therefore remembers our thief substantially
longer than ours remembers theirs. Whether that is an advantage depends on the
belief model — a long tail misleads a belief that reads absolute intensity, which
is why `decay_all` carries a cutoff — and the friendly was inconclusive on the
point, because neither officer captured once.

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

## 7. Closing the loop: the defect an opponent found, and what fixing it did not fix

The strongest evidence in this project came from losing.

### 7.1 The defect

We lost the counted series to imreeyal 30–90 after beating them 70–50 twice the
same evening in friendlies. Their operator then explained the gap: in a friendly
they run their real brain in sub-games 1–2 and a practice brain in 3–6; in a
counted series the real brain plays all six. They volunteered this. Without it we
would have drawn conclusions from four windows of a brain that was not trying.

The signed logs showed the three lost thief windows were not three failures but
one failure three times. Our thief walked into `(6,0)`, played STAY five times, and
was sealed by **two** of their fourteen barriers. `_safety()` ranked survival
probability above open exits, so a corner reported "safe" right until it was not.

### 7.2 The fix, and what we measured before claiming anything

Open exits now rank directly below proof and above preference, but only where the
ply count has saturated at the horizon — below the horizon survival still decides,
a constraint two existing tests caught us violating. Over 400 random states: 10%
of decisions change, mean open exits of the chosen cell rise 3.68 → 3.78, and in
**zero** cases does the new ranking choose a more cramped cell.

An earlier docstring described this failure as "one sub-game in three hundred."
Live it was three in three. The estimate came from an arena that could not produce
the position — the arena had no officer that would spend a wall to seal a low-exit
cell, so it certified a rate for a scenario it was structurally unable to generate.
That is the sharpest methodological lesson of the project: **a benchmark that cannot
produce the failure will always report that the failure is rare.**

### 7.3 Live validation, 24/08

imreeyal agreed, on request and with nothing in it for them, to field their real
stack in **all six windows** — including the officer that did the sealing. This is
the same test that produced the 30–90, re-run against the same opponent.

| | before (counted, 20/08) | after (friendly, 24/08) |
|---|---|---|
| series | **30–90 loss** | **47–47 draw** |
| our thief windows | captured 3 / 3 | **survived 3 / 3** |
| corner entries | 3 | **0** |

Across all six thief windows played that day — three against imreeyal and three
against anrbj666 — the thief entered a corner **zero times**. The defect is closed.

### 7.4 What the score hides, and why we are recording it

The 47–47 credits us with more than we earned.

| opponent | STAYs / 35 | longest STAY run | distinct cells |
|---|---|---|---|
| anrbj666 | 12–20 | 4–10 | 10–13 |
| imreeyal | **23–27** | **21–25** | **6–8** |

Against imreeyal's officer specifically our thief nearly freezes: twenty-five
consecutive STAYs in two of three windows, six distinct cells in a thirty-five step
game. **It survived as a stationary target their officer did not find** — which is
not the same as surviving because it moved well. Since a peer deposits its full
0.9 at its own cell every turn, and the maximum cell of a transmitted field is
therefore the emitter's current position, a thief that stands still is broadcasting
a stable beacon at itself. That it was not punished says as much about their
officer's search as about our thief.

**Corners fixed; mobility not.** The safety ranking refuses the trap but still
prefers standing still to taking ground, and under a high-pressure officer that
preference dominates. This is left as a stated, measured, open weakness rather
than repaired in the hours before submission, where an unmeasured change to the
graded tree is the larger risk.

### 7.5 A methodological note on decoy loadouts

Our three police sub-games against anrbj666 were byte-identical — same move
sequence, same hash, all three — because their friendly thief is deterministic and
so is our officer. The thief windows differed, so their officer does vary. A
six-sub-game friendly therefore yielded **four distinct games, not six**.

Generalised: when one side fields a practice brain and the other fields its real
one, the shakeout under-tests the side playing seriously, and its length overstates
its evidential value. Both opponents disclosed their loadout split unprompted, and
that disclosure was worth more to us than either result.

### 7.6 Barriers

Our officer placed 27 barriers across the anrbj666 series — nine per police window,
against **zero in fourteen** before the `wall_threshold` change described in §3.
The gate now opens. It converted none of them: one capture claim per window, no
capture, against either opponent. This matches the arena measurement against a
careful thief (0.00–0.02) rather than contradicting it. Walls do not beat a thief
that refuses cramped ground, and both of these refuse.
