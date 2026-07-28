# Prompt engineering log

This project was built with an AI coding agent, as the course intends. The
submission guidelines ask for the prompt log; what follows is the honest version,
including the prompts that produced work we had to throw away, because those were
the instructive ones.

## The governing lesson

**Specifying the acceptance criterion mattered far more than specifying the
solution.** Every prompt below that named a *measurable outcome* produced usable
code on the first attempt. Every prompt that described a *mechanism* produced code
that ran, looked reasonable, and was wrong in a way we only found by measuring.

---

## Phase 1 — Requirements before code

> Read the whole project book, including every appendix. Appendix F is the single
> source of truth for numeric values; Appendix E lists 55 mandatory rules. Produce
> a compliance table mapping each rule to a component before writing any code.
> Where the book and the reference simulator disagree, the book governs — list the
> disagreements explicitly.

This produced `RULES-COMPLIANCE.md` and surfaced the two genuine book-versus-code
conflicts (multiplicative scent decay; six sub-games per series) *before* they
became rework. Loading the requirements first was the highest-leverage decision in
the project.

## Phase 2 — Architecture

> Design a modular architecture where `domain` performs no I/O and imports
> nothing outward, `infra` is the only package that touches a socket or a
> subprocess, and every consumer enters through one SDK class. Keep every file
> under 150 lines. Explain each boundary in the module docstring, in terms of what
> becomes possible rather than what the layer contains.

The 150-line ceiling did real work. It forced `guards.py` out of `gatekeeper.py`
and `barriers.py` out of `police_brain.py` — both of which turned out to be the
right seams, and both of which became independently testable.

## Phase 3 — The interoperability constraint

> Before writing the protocol: our peer must play against agents built from the
> course reference simulator. Determine exactly which field names and which signed
> dictionary keys are load-bearing for interoperability, freeze them, and add a
> test asserting the frozen key sets.

This was the prompt that saved the project. The signed-terms dictionary is
compared with `==` by the reference implementation, so a single extra key — the
scent-falloff selector we wanted — would have made us unable to shake hands with
anybody in the league. That constraint then shaped ADR-8: our extensions live in
the sealed payload, which only we hash.

## Phase 4 — Strategy, and the prompt that failed

First attempt:

> Implement a police brain that pursues using the belief map and places barriers
> to trap the thief.

Plausible, and it produced code that ran cleanly and **captured 0 % of matches**.
The barrier planner demanded a meaningful immediate reduction in the thief's
reachable region, and on an open board sealing one cell removes exactly one cell,
so it never built a single wall in thirty matches. The officer's defining ability
went entirely unused and nothing in the code looked wrong.

The corrective prompt:

> The barrier planner never fires because a wall's immediate cell-count gain is
> always 1 on an open board. Re-derive the valuation from what actually wins
> games: anchoring against existing walls and board edges so segments grow into
> fences, cut vertices, and the probability the cell is occupied — since sealing an
> occupied cell is itself a capture. Add vetoes against walling ourselves away from
> the thief. Then sweep the threshold and report capture rate against two opponent
> archetypes.

0 % → 32 % against our own strongest thief, 13 % → 57 % against a reference-style
one.

**The lesson:** "trap the thief" is a description of intent. "Cells removed plus
anchoring plus cut-vertex bonus, vetoed by self-isolation, measured against two
archetypes" is a specification. Only the second is checkable.

## Phase 5 — The benchmark that lied

> Benchmark the strategies over 30 matches and report the capture rate.

It reported **100 %** — and it was one match repeated thirty times. Both
strategies are deterministic, the seed fed only an unused RNG, so nothing varied.

> Both brains are deterministic, so a fixed opening makes every match in a run
> identical and the reported rate meaningless. Sample the start positions per seed,
> rejecting pairs that begin within two steps, and explain in the code why.

The honest numbers were 32 % and 57 %. We would have shipped a false claim in the
report otherwise, which is the kind of error that is invisible until someone
checks — and which is exactly what the research report is for.

## Phase 6 — Verbal layer

> The move must never be model-chosen (rule 25). Design the deception layer so
> that lying is a *resource decision* rather than a fixed rate: model what the
> opponent's own lie detector would conclude about us from the scent we are
> visibly leaving, and spend credibility only when a turn is decisive.

This produced the credibility-banking planner, which we think is the most original
part of the submission. The key insight came from writing the *detector* first:
once we had a lie detector, we could point it at ourselves.

## Phase 7 — Tests as specification

> Write tests that state the property, not the implementation. Where a test
> encodes a rule from the book, name the rule in the test name or docstring.

Two tests found real bugs. The state-machine test exposed a missing transition —
a match ending on our own move had no legal path to the audit phase. The
belief-filter test exposed that a naive prediction step leaked probability mass
through walls, silently wasting every barrier the officer paid for.

Four tests failed because the *test* was wrong, and each was worth the time: the
best was a barrier-planner scenario where the planner correctly refused to seal a
cut vertex because the officer was standing on the wrong side of the wall. The
code was right and our assertion was naive.

## What we would tell the next team

1. **Load the requirements before the code.** A compliance table written first is
   worth a week of rework avoided.
2. **Name the acceptance criterion in the prompt.** "Trap the thief" gets you code
   that runs. "Capture rate above X against these two archetypes" gets you code
   that works.
3. **Distrust a clean benchmark.** 100 % should have been implausible on its face.
   Ask what varies between runs before believing any rate.
4. **Constraints improve output.** The 150-line ceiling and the frozen wire format
   both produced better architecture than an unconstrained prompt would have.
5. **Ask for the docstring to explain *why*.** Requesting rationale rather than
   description is what turned the comments into something worth reading, and it
   repeatedly exposed decisions that could not actually be justified.
