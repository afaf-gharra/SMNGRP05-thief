# PRD — scent trails and the belief filter

## Background

Neither agent can see the other. The book's answer is stigmergy: agents leave
pheromone trails, and the environment becomes the shared notice-board. The
crucial property is that a trail is emitted by the act of moving and **cannot be
forged** — it is the only honest witness in a game where every sentence may be a
lie.

## Requirements

* **R1** Each turn a peer deposits a 5×5 window, peak 0.9, around itself.
* **R2** The whole field decays once per turn by `τ(t+1) = max(0, (1−ρ)·τ(t) + Δτ)`
  with ρ = 0.10 — **multiplicative**, per the book (see `RESEARCH-REPORT.md` §6).
* **R3** Deposits merge by maximum, so revisiting refreshes rather than doubling.
* **R4** Only the resulting *field* is transmitted, never the centre cell.
* **R5** Each peer maintains `b(s)` over the opponent's cell and updates it by
  predict-then-observe every turn.
* **R6** The prediction step must respect barriers and the negotiated move set.
* **R7** A hint updates the belief only through a learned trust coefficient.

## Input / output

`SmellField.deposit(cell, intensity)` mutates the field;
`snapshot() -> {"r,c": float}` is what crosses the wire.
`BeliefGrid.predict(barriers, stay_allowed)` then `observe_smell(cells)`;
queries are `most_likely()`, `top_cells(n)`, `mass_within(cell, radius)`.

## Constraints

**R6 is where a naive implementation quietly fails.** A 3×3 smear leaks
probability mass through walls, which means every barrier the officer paid for is
silently wasted inside its own belief model. Our prediction walks the real graph.
Asserted directly: starting from certainty south of a full-width wall, eight
prediction steps leave *exactly zero* mass north of it.

Trail lifetime is a design target, not an accident. At ρ = 0.10 a deposit crosses
half-peak near turn 7, giving a six-to-seven-turn readable history — long enough
to be tactically useful, short enough that the board does not saturate into a
uniform smell of everything.

## Alternatives considered

*Particle filter* — unnecessary on 49 cells; an exact grid filter is cheaper and
exactly correct.

*Trusting the strongest scent cell directly* — works until the opponent stands
still or doubles back; the filter integrates evidence over time instead.

*Ignoring hints entirely* — throws away real information. Weighting them by a
learned honesty estimate is strictly better, and lets a liar's own words work for
us once the estimate drops below one half.

## Success criteria and test scenarios

| Scenario | Expected |
|---|---|
| Gaussian emission | reproduces the book's figure to 2 d.p. |
| Deposit then decay | 0.9 → 0.81 → 0.729 |
| Seven turns after a deposit | between 0.40 and 0.45 (half-peak) |
| Deposit below the agreed minimum | refused |
| Junk or off-board cells in a received field | ignored |
| Prediction against a full-width wall | zero mass crosses |
| Hint at trust 0.5 | belief unchanged |
| Hint at trust 0.1 | named region *loses* mass |
