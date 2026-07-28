# Task board

Status: `[x]` done · `[~]` in progress · `[ ]` not started.
Definition of done for every task: behaviour observed end to end, covered by a
test, `ruff` clean, and the file under 150 lines.

## Stage 1 — base logic (book ch.3)
- [x] Board geometry: bounds, orthogonal moves, barrier blocking
- [x] Flood fill, true shortest path, cut-vertex detection
- [x] `OwnGameState`: local truth, move log, barrier quota
- [x] Capture by contact, by sealing (rule 46), by enclosure (rule 47)
- [x] Scoring table, series aggregate, tie rule
- **Milestone:** two agents move legally, an illegal move is refused, overlap captures

## Stage 2 — MCP transport (book ch.2)
- [x] Per-peer FastMCP server with four tools and thread-safe inboxes
- [x] Client to the opponent URL with bounded retry
- [x] Port-in-use detected early with an actionable message
- [x] Loopback transport double with the identical interface
- **Milestone:** a message leaves peer A and is decoded correctly by peer B

## Stage 3 — strategy (book ch.6)
- [x] `BeliefGrid`: predict/update, barrier-aware motion model
- [x] `ArchitectPolice`: expected distance + containment + capture claims
- [x] `OpenSpaceThief`: region maximisation, dead-end and contact penalties
- [x] Barrier planner: anchoring, cut vertices, occupancy, self-isolation vetoes
- [x] Config-selectable brains via dotted selector
- [x] Benchmark harness with sampled starts
- **Milestone:** the officer reaches a known target by the shortest legal route

## Stage 4 — language and scent (book ch.4, ch.6)
- [x] `SmellField`: 5×5 emission, multiplicative decay, wire snapshot
- [x] Hint parser: bearings, landmarks, centre/edge/corner, negation
- [x] `TrustEstimator`: Beta-Bernoulli honesty model, specificity-weighted
- [x] `BluffPlanner`: credibility banking, self-scoring feedback loop
- [x] Template talker (zero tokens) and three optional model providers
- **Milestone:** a hint is produced, parsed back, and cross-checked against scent

## Stage 5 — public exposure (book ch.2)
- [x] Bind `0.0.0.0` so a tunnel can reach the server
- [x] Tunnel instructions and configuration fields
- [ ] Fixture 1: tunnel up, opponent connected, series played
- [ ] Fixture 2: a different opponent team
- **Milestone:** a remote machine completes a full series against us

## Stage 6 — cryptography (book ch.5)
- [x] Commit-reveal over canonical JSON, `secrets` nonces
- [x] Signed terms handshake, mismatch names the differing keys
- [x] Step-zero hardware, model and commit-hash declaration
- [x] Mutual end-of-match audit that attributes blame
- [x] Phase machine rejecting illegal transitions
- **Milestone:** a one-byte edit anywhere is detected and voids the match

## Stage 7 — reporting shell (book ch.7, ch.9, Appendix A)
- [x] Gatekeeper: quota, token bucket, DOS breaker, queueing
- [x] Gmail sender, `gmail.send` scope only, JSON attachment
- [x] Four artifacts with cryptographic locks and derived filenames
- [x] Live window: heatmap, turn banner, local truth only
- [x] Replay auditor: `Verified OK` / `TAMPERED`, jump to first failure
- [x] Screenshots captured from a real match
- **Milestone:** a completed series emails a machine-readable report

## Cross-cutting
- [x] Coverage ≥ 85 % (currently 90 %), `ruff` clean, `uv` only
- [x] PRD, PLAN, TODO, five mechanism PRDs, strategy guide, research report
- [x] Rule-by-rule compliance map for all 55 mandatory rules
- [x] Secrets excluded from git from the first commit
- [ ] Annotated `v1.0-submission` tag pushed to both repositories

## Known limitations
- Fixtures against other teams are pending; the protocol is exercised end to end
  against ourselves and the reference-style baselines.
- The hint parser is keyword-based by design (deterministic, replayable, instant).
  It will not understand an opponent's free-form metaphor, which costs us evidence
  but never correctness — an unparsed hint simply carries zero weight.
- Tuning was optimised against two opponent archetypes. A genuinely novel strategy
  may expose weights we have not sampled; `scripts/arena.py` is how we would find out.
