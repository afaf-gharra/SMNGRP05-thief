# Product Requirements — `p2p-chase`

**Group `SMNGRP05`** · version 1.00 · target: the 2026 course league

## 1. Problem and context

Two teams must field autonomous agents that play cops-and-robbers against each
other across the public internet, with **no central server, no referee, and no
shared memory**. Each agent sees only its own position; the opponent is inferred,
never observed. Either side may lie in conversation.

The hard part is not the chase. It is that both agents must arrive at the *same*
result, independently, while each has a standing incentive to cheat and no
authority exists to stop them. A design that assumes good faith anywhere fails.

**Users.** (1) Our own team, operating the agent in league fixtures. (2) The
opposing team's agent, which is adversarial and whose implementation we do not
control. (3) The lecturer, who receives machine-parsed reports and audits code.

## 2. Goals and success metrics

| # | Goal | Measure | Status |
|---|---|---|---|
| G1 | Complete valid matches against different teams | ≥ 2 required, ≤ 10 counted | protocol ready; fixtures pending |
| G2 | Win more than a reference-style opponent | capture rate as officer, survival as thief | **57 % vs 13 %**; **95 % vs 87 %** |
| G3 | Never lose on a technicality | zero forfeits from crash, deadlock or malformed report | deadline + watchdog + phase machine; 250+ tests |
| G4 | Both peers always agree on the result | identical `mutual_agreement.sha256` | asserted end-to-end |
| G5 | Score well on computational fairness | tokens consumed per series | **0** by default |
| G6 | Meet the submission guidelines | coverage, lint, file size, structure | 90 % coverage, ruff clean |

### Acceptance criteria

* **AC1** Two peers on separate machines complete a six-sub-game series over MCP
  through public tunnels, with roles alternating.
* **AC2** Every step verifies at the mutual audit; one altered byte anywhere
  produces `TAMPERED` and voids the match.
* **AC3** Both peers emit four correctly-named JSON artifacts whose symmetric
  content is byte-identical.
* **AC4** The live window never renders the opponent's position.
* **AC5** A match completes with a language model disabled, unreachable, or slow.
* **AC6** `ruff check` clean; coverage ≥ 85 %; no source file over 150 lines.
* **AC7** No secret is present in any commit.

## 3. Functional requirements

**FR1 Physics.** 7×7 grid, four orthogonal moves or stand still, no diagonals.
Officer may seal one adjacent cell instead of moving, up to 14 times,
irreversibly. Sealing the thief's cell is a capture. A thief with no legal move
is captured.

**FR2 Observation.** Each peer emits a 5×5 scent window (peak 0.9) around itself
each turn; the whole field decays multiplicatively by ρ = 0.10 per turn. Peers
exchange fields, never coordinates.

**FR3 Language.** Free natural language only. No numeric position protocol. Hints
may be false; the honesty flag is committed *before* the hint is revealed.

**FR4 Integrity.** Every step sealed as `SHA-256(canonical(payload) ‖ nonce)`;
nonces revealed only at the final mutual audit.

**FR5 Agreement.** Both peers sign identical terms before play; any mismatch
aborts before the first move.

**FR6 Decision.** The move is computed in Python. A model may write hints and
profile the opponent, never navigate.

**FR7 Reporting.** Four JSON artifacts per match, named from `game_id`, emailed
to the lecturer as an attachment via a send-only Gmail scope.

**FR8 Observability.** A live local-truth window and a replay auditor that
re-verifies every step.

## 4. Non-functional requirements

| Area | Requirement |
|---|---|
| Reliability | No unbounded wait anywhere. A crash in one sub-game must not lose the series. |
| Security | Send-only mail scope; no secret in git; nonces secret until audit. |
| Performance | A turn decides in well under a second on a laptop; a full series in minutes. |
| Cost | Zero tokens by default; any model use is throttled, deadlined and optional. |
| Portability | Windows, macOS, Linux; standard library plus `fastmcp`. |
| Maintainability | ≤ 150 lines per file, single-responsibility modules, SDK entry point. |

## 5. Assumptions, dependencies, constraints

* The opponent implements the reference wire protocol. **This constrains us
  hard**: the signed-terms dictionary and the `TurnMessage` field set are frozen,
  because adding a field would make us unable to shake hands with anyone.
* Both peers are reachable through a tunnel during a fixture.
* Where the book and the reference code disagree, the book governs — see
  [RESEARCH-REPORT.md](RESEARCH-REPORT.md) §6 for the two cases and how we
  resolved them.

## 6. Out of scope

Reinforcement learning (optional per the book; the seam is open). More than two
agents. Boards other than square grids. A tournament server — there is none, by
design. Persisting matches across process restarts beyond the watchdog snapshot.

## 7. Milestones

| Stage | Deliverable | State |
|---|---|---|
| 1 | Board, movement, capture rules, in one process | done |
| 2 | Two peers over MCP on localhost | done |
| 3 | Strategy module against known positions | done |
| 4 | Natural language, scent, belief, deception | done |
| 5 | Public tunnels | ready; exercised per fixture |
| 6 | Commit-reveal, step-zero declaration | done |
| 7 | Gatekeeper, Gmail, GUI, replay auditor | done |
