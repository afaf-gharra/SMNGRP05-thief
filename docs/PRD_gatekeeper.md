# PRD — the API Gatekeeper

## Background

An autonomous agent with a bug is perfectly capable of firing thousands of
requests a minute and getting its owner's mail account suspended before anyone
notices. The submission guidelines require a single centralised gate for external
calls; the book specifies what has to sit behind it.

## Requirements

* **R1** Every outbound external call passes through one object. No direct calls
  anywhere in the codebase.
* **R2** Three cumulative gates, failing fast: daily quota → token bucket → DOS
  breaker.
* **R3** Overflow is **queued**, not dropped — a late report still scores, a
  dropped one costs league points.
* **R4** Transient failures retry with backoff, bounded.
* **R5** All limits come from `rate_limits.json`, never hard-coded.
* **R6** State is observable and folded into the match report.

## Input / output

`ApiGatekeeper(limits, service).execute(call, *args, **kwargs)` returns the
call's result or raises `RateLimited`. `status()` reports counters, available
tokens, quota remaining and breaker state.

## Constraints

The token-bucket rule is `tokens ← min(C, tokens + r·Δt)`, allowed iff
`tokens ≥ 1`. It separates the sustainable rate `r` from the burst `C`, so silence
is rewarded with capacity while a runaway loop is throttled to exactly `r`.

**Terminology.** "Token" here is a *rate* token and has nothing to do with
language-model tokens. The book warns explicitly about the collision; the two
never appear in the same code path in this project.

The DOS breaker **latches**. Time alone does not re-arm it — a human must look at
the logs first, because the condition it detects is a bug in us, not load. It
deliberately sacrifices the reports still queued in order to save the account
they would be sent from.

## Alternatives considered

*A fixed sleep between calls* — wastes throughput when idle and still bursts
after a pause.

*A leaky bucket* — smooths output but forbids the legitimate burst of sending
four artifacts at once at the end of a match.

*Dropping on overflow* — cheapest to implement and exactly wrong: the item being
dropped is a league report.

## Success criteria and test scenarios

| Scenario | Expected |
|---|---|
| Bucket starts full | a fresh agent may act immediately |
| Burst of `C` then one more | first `C` pass, the next is throttled |
| Quiet period | capacity restored proportionally to elapsed time |
| Two transient failures then success | retried, succeeds, counted once |
| Persistent failure | `RateLimited` after the retry budget |
| Daily quota exhausted | refuses rather than risking the account |
| Runaway burst | breaker latches and stays shut until manually reset |
| Sustained traffic above `r` | waits for a token; does not drop the call |
