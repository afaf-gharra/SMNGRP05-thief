# Friendly vs aviayeli — 27/08/2026. 90-30, six sub-games, first attempt each.

    sg1  we thief    survival  SMNGRP05  10 -  5
    sg2  we police   capture   SMNGRP05  20 -  5
    sg3  we thief    survival  SMNGRP05  10 -  5
    sg4  we police   capture   SMNGRP05  20 -  5
    sg5  we thief    survival  SMNGRP05  10 -  5
    sg6  we police   capture   SMNGRP05  20 -  5
    ------------------------------------------------
                              90 - 30    sub-games 6 - 0

0 audit warnings, 0 duplicate drops, 0 errors. Friendly: the report went to our
own address and the league address was on no recipient line.

## Why the officer converted here and nowhere else

Our research report records a measured negative result: the officer spends
barriers and converts none. Across twelve sub-games against bb-ai-12 it caught
nothing, and neither did theirs. Here it captured three times out of three.

That is the same officer. What changed is the thief it was chasing -- and the
symmetry holds in the other direction: our thief survived 35 in all three
sub-games it played, including two in which their officer claimed a capture on
every one of its 34 turns and never landed one. Sixty-eight claims, no
conversion.

So this result does not overturn the negative finding; it locates it. The
officer does not catch a careful thief. It does catch one that is not.

## What the pre-match exchange found

Five defects between the two groups in one evening, none found by the team
that owned it working alone -- both repositories had green suites, enforced
line ceilings, clean linters and matching digests throughout:

* ours: min_games_to_pass — no, theirs, a קבוע field at 1 for ten days
* ours: no check at all on the values Appendix F marks binding
* ours: the compliance checker keyed on filename, blind to 205 artifacts
* ours: 79 artifacts whose agreed_between disagrees with their own game_id,
        37 of them carrying ROLES where group codes belong (none filed)
* theirs: inbound audits accepted, held in memory, persisted nowhere

The transcription of Appendix F that started it is in the thread; the checker
it produced is `tools/appendix_f_check.py`.

Archived separately because a counted series against the same group reuses
these filenames.
