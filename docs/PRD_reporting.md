# PRD — the four artifacts and automatic reporting

## Background

The lecturer builds the league table from machine-parsed reports. Both teams
report the same match independently, and if the two reports contradict each other
the match is void **for both** — so agreement between them is not a nicety, it is
the requirement.

## Requirements

* **R1** Four artifacts per match: declaration, config, log, result.
* **R2** Every filename derived from `game_id`; per-sub-game files carry `g<NN>`.
* **R3** The config artifact carries a SHA-256 lock over the agreed terms.
* **R4** The result carries a mutual signature both peers compute identically.
* **R5** The result is emailed as a JSON **attachment**, never as free text.
* **R6** The Gmail token requests `gmail.send` and nothing more.
* **R7** Each match records the commit hash that played and the tokens consumed.
* **R8** Artifacts are written to disk **before** the email is attempted.

## Input / output

`emit_series(config, logs_dir, series) -> result_dict`, writing into
`logs/<group_id>/`. `GmailReporter.send_result(result, filename)` returns a
status dictionary and never raises into the match.

## Constraints

**R4 is the subtle one.** Wall-clock timestamps and per-peer token counts
legitimately differ between the two machines, so a signature covering the whole
report would *never* match. It therefore covers only the symmetric facts: roles,
outcomes, winners, scores and the aggregate. A test feeds two peers deliberately
different timestamps and token counts and requires the same hash.

**R8** matters because a mail failure must never destroy the evidence that a
match happened. The artifacts are already on disk and can be sent by hand.

Files land in a per-group subfolder because roles alternate across a series, so
`group_id` — not role — is the only stable discriminator when two peers happen to
share a machine during development.

## Alternatives considered

*One combined report file* — the book specifies four, with genuinely different
lifetimes; static team data would then be duplicated into every sub-game log.

*Reporting from one side only* — explicitly forbidden. A team that does not
report scores nothing for that match even if it won on the board.

*Free-text email* — rejected by the grader's parser, and scores zero.

## Success criteria and test scenarios

| Scenario | Expected |
|---|---|
| Both peers finish a series | identical `mutual_agreement.sha256` |
| Different timestamps and token counts | signature unchanged |
| Different outcome | signature changes |
| Group order reversed between peers | identical `groups` block and declaration hash |
| Same terms, different sub-game number | identical `config_sha256`, different filename |
| Any sub-game audit failed | `confirmed: false` |
| Gmail disabled or unavailable | artifacts still written; status reported, no raise |
