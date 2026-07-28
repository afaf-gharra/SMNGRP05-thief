# PRD — the strategy module

## Background

The strategy is the graded component and the only thing that decides matches. The
book requires it to be a separate module with a clean seam, and requires the move
to be algorithmic rather than model-chosen.

## Requirements

* **R1** The move is computed in deterministic Python; a model is never consulted
  for it.
* **R2** The brain is selectable by configuration without touching the engine.
* **R3** Only legal actions are ever emitted; an illegal one is refused locally.
* **R4** The officer manages a 14-barrier budget across a 35-step horizon.
* **R5** The thief must handle enclosure honestly and immediately.
* **R6** Decisions must be reproducible for audit given the same inputs.

## Input / output

In: a `TurnContext` — own state, belief, trust estimate, the opponent's last
sentence, the remaining budgets, and this brain's tuning block.

Out: `(MoveType, Direction | None, target, rationale, claims_capture)`. The
rationale is sealed into the audit log.

## Constraints

Under a second per turn on a modest laptop. No I/O, no global state. `argmax`
ties are broken by cell order so two replays of the same log agree exactly.

## Alternatives considered

*Q-learning* — the state space is finite, so it is feasible. Rejected because the
course did not teach it, the book explicitly calls it one option among equals,
and a deterministic policy we can sweep — and an examiner can read — was the
better engineering trade here. The seam stays open if we change our minds.

*Minimax or expectimax* — the opponent's position is unknown, so the tree is over
beliefs rather than states, and the branching factor buys little.

*Greedy distance* (the reference policy) — implemented as `strategy/baselines.py`
and used as the yardstick rather than as a candidate: 13 % capture against our
57 %.

## Success criteria

Measured in `RESEARCH-REPORT.md`. Headline: 57 % capture as officer against a
reference-style thief where a reference-style officer manages 13 %, and 95 %
survival as thief against a reference-style officer where a reference-style thief
manages 87 %.

## Test scenarios

| Scenario | Expected |
|---|---|
| Thief adjacent, belief confident | officer steps on and claims |
| Belief uniform | officer moves but claims **nothing** (no position leak) |
| Thief far, walls anchored nearby | officer builds rather than chases |
| Wall would cut us off from the thief | refused |
| Wall on a cut vertex, from the correct side | chosen |
| Thief sealed in | concedes, honestly, at once |
| Officer boxed in with no quota left | holds instead of crashing |
| Same state presented twice | identical decision |
