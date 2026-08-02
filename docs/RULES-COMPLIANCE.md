# Compliance map — Appendix E, all 55 mandatory rules

Every binding rule from the project book's Appendix E, mapped to the code that
implements it and, where the behaviour is testable, the test that proves it.

## 1. Network architecture, decentralisation, local epistemology

| # | Rule | Implementation | Evidence |
|---|---|---|---|
| 1 | Police and thief run in two fully separate processes | Two repositories, two `config/<role>/` trees, one `PeerRuntime` per process | `README` §intro; `cli.py` |
| 2 | No shared memory or variables between the sides | Communication is only `McpTransport`; `domain` holds no cross-peer state | `peer/turn_handler.py` — the *only* inbound path |
| 3 | The orchestrator is the single entry point to subsystems | `peer/orchestrator.py` | `test_a_broken_transport_becomes_a_scored_technical_loss` |
| 4 | Game phases managed by a proper state machine | `domain/phases.py` | `test_scoring_and_phases.py` |
| 5 | Illegal state transitions are rejected | `GamePhaseMachine.to` raises `PhaseError` | `test_an_illegal_transition_raises_immediately` |
| 6 | Deadline tracking prevents freezing while waiting | `peer/deadline.py`, applied to every wait | `test_a_deadline_expires_and_is_counted` |
| 7 | A watchdog monitors crashes and extracts data | `peer/watchdog.py`, daemon thread + state persistence | `test_a_frozen_loop_triggers_a_controlled_shutdown` |
| 8 | The live UI shows local truth only | `peer/summary.live_view` returns no opponent position | `gui/board_view.py` accepts no such field |
| 9 | The live UI never shows the full objective board | Belief heatmap only; no bird's-eye view exists in the process | screenshot in `README` §5 |
| 10 | A tunnel exposes the local server publicly | Binds `0.0.0.0`; `network.host` configurable | `README` §Playing over the public internet |

## 2. Spatial mechanics, physics, board constraints

| # | Rule | Implementation | Evidence |
|---|---|---|---|
| 11 | The config file is byte-identical on both sides | Signed-terms handshake; mismatch names the differing keys | `domain/negotiation.py`; `test_config_and_terms.py` |
| 12 | Minimum values may be raised, never lowered | `config/*/game.json` ships Appendix F minimums; `validate_agreement` range-checks | `shared/terms.py` |
| 13 | Movement only in orthogonal directions | `constants.ORTHOGONAL`, `move_set` in the signed terms | `test_default_move_set_is_the_four_orthogonals` |
| 14 | No diagonal moves | `Board.step` refuses a direction outside the move set | `test_a_direction_outside_the_move_set_is_illegal` |
| 15 | Every barrier placement is openly declared | `TurnMessage.barrier_placed`, set from `state.last_barrier()` | `peer/sealing.build_turn_message` |
| 16 | No lying about a barrier's location | The declared cell is the sealed cell; both are in the audited payload | `peer/turn_sender.send` |

## 3. Cryptography, log integrity, zero knowledge

| # | Rule | Implementation | Evidence |
|---|---|---|---|
| 17 | Commit-reveal based on SHA-256 | `domain/crypto.py` | `test_crypto.py` |
| 18 | The nonce stays secret until the end of the match | Only `commit` is in `TurnMessage`; nonces revealed in `AuditPayload` | `domain/protocol.py` |
| 19 | Any hash mismatch at audit forfeits the match | `audit_records`; `Outcome.TAMPER_FORFEIT` scores 0-0 | `test_the_audit_names_the_tampered_step` |
| 20 | A replay viewer verifies the match log | `gui/replay_app.py`, `gui/replay_data.py`, plus headless `verify` | screenshots; `test_reporting.py` |
| 21 | Capture declarations must be truthful | `GameRules.is_captured` answers from sealed local truth | `test_a_capture_claim_is_answered_honestly` |
| 22 | No false capture claims | The claim and the position are both in the sealed payload | `peer/turn_sender._capture_claim` |
| 23 | The scent emission model is locked before play | `describe_scent_model` — formula **and** a worked number — sealed at step zero | `test_the_scent_model_ships_a_worked_numeric_example` |
| 24 | A cryptographic hardware declaration precedes play | `sealed_spec_record` (step 0), sealed before move one | `test_the_step_zero_record_seals_the_commit_that_played` |

## 4. Strategy, language, public network

| # | Rule | Implementation | Evidence |
|---|---|---|---|
| 25 | The model does not decide the move *(recommendation)* | `_decide_move` is pure Python; the talker runs afterwards | `strategy/base.py`; `README` §3 |
| 26 | Communication in free natural language only | Template and model talkers both emit prose | `strategy/talk/templates.py` |
| 27 | No direct numeric position protocol | `TurnMessage` carries a scent *field* and claims, never a position handout | `test_no_position_is_ever_sent_in_the_clear` |
| 28 | Token-bucket rate limiter for report sending | `shared/rate_limiter.py`, wired into the Gatekeeper | `test_gatekeeper.py` |
| 29 | DOS detector protecting network resources | `shared/guards.DosDetector`, latching breaker | `test_a_runaway_loop_latches_the_breaker` |
| 30 | Send-only permission for Gmail | `SCOPES = ["…/auth/gmail.send"]`, nothing else | `infra/gmail_sender.py` |

## 5. League fairness, administration, competition integrity

| # | Rule | Implementation | Evidence |
|---|---|---|---|
| 31 | Play the minimum number of matches vs different teams | `league.min_games_to_pass = 2`; fixtures tracked in the submission form | `config/*/game.json` |
| 32 | Report results automatically via Gmail | `ChaseSdk.play_series` → `GmailReporter.send_result` | `sdk/sdk.py` |
| 33 | The report is standard JSON | `report/artifacts.py`; four typed artifacts | `test_reporting.py` |
| 34 | No free-text report; JSON attachment only | `add_attachment(..., subtype="json")`; body is a courtesy summary | `infra/gmail_sender.py` |
| 35 | Both teams agree and each sends its own report | Mutual signature over symmetric facts only | `test_the_two_reports_agree_exactly` |
| 36 | Comprehensive mutual log audit at the end of each match | `peer/audit.exchange_audit`, both directions | `test_the_mutual_audit_completed_on_both_sides` |
| 37 | Declare the number of matches already played | `league` block in the signed terms; declared in the handshake | `shared/terms.py` |
| 38 | No false declaration of match count | The declared value is inside the signed terms both peers hash | `domain/negotiation.py` |
| 39 | Never push secrets or credentials | `.gitignore` from the first commit | `.gitignore` |
| 40 | Credentials and secrets are git-ignored | `credentials.json`, `token.json`, `.env`, `*.pem`, `*.key` | `.gitignore`; `.env-example` |
| 41 | Tag the submission with a documented Git tag | Annotated `v1.0-submission` | `git show v1.0-submission` |
| 42 | A comprehensive academic report in the repository | `README.md` §1–6 plus `docs/` | this repository |
| 43 | Fill the Moodle form, save as PDF, move no field | `SMNGRP05-ex12.pdf` | submitted separately |
| 44 | Each group member submits in Moodle separately | administrative | — |
| 45 | A unique eight-character group code | `SMNGRP05`, used in every artifact and filename | `config/*/game.toml` |

## 6. Completions found when cross-checking the book

| # | Rule | Implementation | Evidence |
|---|---|---|---|
| 46 | A barrier placed on the thief's cell is a capture | Barrier moves carry a `capture_claim`; the officer prices occupancy highly | `test_sealing_a_probably_occupied_cell_scores_highly` |
| 47 | A thief with no legal move is captured | `GameRules.is_sealed_in`; the thief concedes honestly and immediately | `test_a_thief_with_no_legal_move_is_captured` |
| 48 | Score every ending per the table (20/5, 5/10, 0/0) | `domain/scoring.py` | `test_scoring_and_phases.py` |
| 49 | Two repositories, cross-linked, four links in the JSON | `README` cross-link; `identity_from_config` carries both repo URLs | `docs/sample-run/declaration_*.json` |
| 50 | Each repository holds README, config, PRD, PLAN, TODO | `docs/` and `config/` | this repository |
| 51 | Send the automatic reports to the lecturer's address | `email.recipient = rmisegal+uoh26finalgame@gmail.com` | `config/*/game.toml` |
| 52 | Only one match counts per opponent; warm-ups allowed | Operational; counted matches recorded in the submission form | `docs/PRD.md` §2 |
| 53 | Record the commit hash that played, per match | `gitinfo.commit_hash` sealed into step zero and into the result | `shared/gitinfo.py` |
| 54 | Report total tokens consumed | `tokens_total` per sub-game and `tokens_total_series` | `report/emit.py` |
| 55 | Self-assessment is for code quality, not the league result | Stated on the submission form | — |

## Prohibitions we hold ourselves to beyond the letter

* The live window has **no code path** that could render the opponent's position —
  the view object does not contain the field, so rule 9 cannot be violated by a
  future edit.
* The signed-terms key set and the `TurnMessage` field set are asserted by tests,
  so a refactor cannot silently break interoperability with the league.
* Deception is confined to the *content* of hints. The honesty flag itself is
  committed before the hint is revealed, so we can never claim after the fact
  that a lie was "meant" as truth.
