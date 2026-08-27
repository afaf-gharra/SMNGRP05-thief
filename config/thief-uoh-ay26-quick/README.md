# `-quick`: a ONE-sub-game warm-up config. Not a league series.

`game.json` here carries **`"num_games": 1`**, not the 6 that Appendix F
Table 18 marks **קבוע**. That is deliberate and it is disclosed here rather
than left for a reader to trip over.

## Why 1 is correct for this config

The book's own `config/game.json` example (printed p.113) carries
`"num_games": 1`, and explains it directly: 1 is the default for a **single
demonstration sub-game**, while a full league series requires the value from
the parameter table. This directory is exactly that case -- warm-up W012
against uoh-ay26, agreed with them in writing, one sub-game, to prove the two
peers could reach each other at all.

## What this config never did

* **It was never counted.** `counted` is not set, and `recipient` is our own
  address -- the league address appears nowhere in it.
* **It was never filed.** The result it produced
  (`result_SMNGRP05-vs-uoh-ay26-W012.json`, one sub-game, 10-5) carries no
  `email` block: nothing was sent.
* **It is not on the submission form.** The seven rows there are the counted
  series; W012 is not among them.

## The configs that matter

Every config used for a counted series carries `num_games = 6`. We audited all
30 `game.json` files across both repositories against all 22 Appendix F
values -- 13 marked קבוע and 9 marked מינימום -- and these two `-quick`
warm-up configs are the only place any value departs from the table.

Method and the transcribed status map are in `docs/RESEARCH-REPORT.md`.
