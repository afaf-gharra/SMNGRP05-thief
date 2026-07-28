# PRD — commit-reveal integrity

## Background

Two peers, each simultaneously player and score-keeper for its own moves, and no
referee. Nothing stops either from rewriting history in its favour after seeing
the other's move. The classic answer is Blum's "coin flipping by telephone":
commit to a choice while it is still sealed, reveal only once the opponent has
locked in theirs.

## Requirements

* **R1** Each step seals `SHA-256(canonical_json(payload) ‖ nonce)`; only the
  digest crosses the wire.
* **R2** Nonces are drawn from `secrets`, never `random`. The action space is five
  moves on 49 cells; a predictable nonce lets the opponent pre-hash every option
  and read the commitment outright.
* **R3** Nonces stay secret until the end-of-match audit.
* **R4** Both peers re-verify the other's entire chain and must agree.
* **R5** Any mismatch is a technical loss, scored 0-0, with no human judgement.
* **R6** The sealed payload covers the move, the position, the honesty flag, the
  hint *and* the reasoning behind it — so we cannot invent a flattering account
  of our own decisions afterwards.

## Input / output

`commit_of(payload: dict, nonce: str) -> str` — 64 hex characters.
`audit_records(records) -> {passed, verified_steps, total_steps, failed_steps}`.

## Constraints

**Canonical JSON is load-bearing.** Sorted keys, `(",", ":")` separators,
`ensure_ascii=False`. Two independently written implementations must hash
byte-identical input, or every honest match would look like fraud. This is the
single most fragile line in the project and it is directly tested.

`compare_digest` is used for the comparison, not `==`.

## Alternatives considered

*Asymmetric signatures* — heavier, needs key distribution, and buys nothing:
identity is already fixed by the fixture, and what we need to prevent is
retroactive edits, not impersonation.

*A trusted third process* — whoever runs it can change outcomes; the book forbids
it and it defeats the point.

*Hashing without a nonce* — trivially broken by a dictionary attack on a
five-action space.

## Success criteria and test scenarios

| Scenario | Expected |
|---|---|
| Clean chain of *n* steps | `passed`, `verified_steps == n` |
| One coordinate altered | `passed == False`, the exact step named |
| One character of the move altered | detected |
| Wrong nonce supplied at reveal | detected |
| Two seals of an identical payload | different nonces and different digests |
| Malformed record (no nonce) | treated as tampered, not a crash |
| Empty log | vacuously verified |

All seven are in `tests/unit/test_crypto.py`; the end-to-end variant is in
`tests/integration/test_full_match.py`, and the visual proof is
`docs/images/replay-tampered.png`.
