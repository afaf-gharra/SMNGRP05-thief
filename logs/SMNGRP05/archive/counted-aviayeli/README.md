# COUNTED series vs aviayeli — 27/08/2026, filed. Won 90-30.

Our ninth counted series, and our second counted win. Filed to the league
address at 22:08, Gmail message id `1a0449f86ec00302`.

    sg1  we thief    survival  SMNGRP05  10 -  5
    sg2  we police   capture   SMNGRP05  20 -  5
    sg3  we thief    survival  SMNGRP05  10 -  5
    sg4  we police   capture   SMNGRP05  20 -  5
    sg5  we thief    survival  SMNGRP05  10 -  5
    sg6  we police   capture   SMNGRP05  20 -  5
    ------------------------------------------------
                              90 - 30    sub-games 6 - 0

    games_played_including_this   SMNGRP05 9, aviayeli 3
    first_meeting_between_groups  true
    diversity_reward_applied      SMNGRP05 true  (+10)
    game_uid  84288aaf-1830-2f1a-8d5c-65bf2c134c80

0 audit warnings, 0 errors. Every audit exchanged and verified both ways.

## Why the declared counts agree, for once

Both numbers arrived the way they were supposed to. Ours: 8 in the greeting,
9 filed. Theirs: 2 in the greeting, 3 filed. Our reporter adds one to BOTH
sides when counted -- `artifacts.py:126` -- and records the opponent's from
their handshake, never from email.

That symmetry is the thing the bb-ai-12 filing hours earlier got wrong: their
greeting carried no field at all, our reader defaulted the absence to 0, added
one, and filed 1 while they filed 2. aviayeli spotted the same trap in their
own declaration before a call was made, added the field as REQUIRED rather
than defaulted, and sent it to us to check first.

## The 56 duplicate turns in sub-game 1

Not a defect. We stopped our peer at 21:50 to take their rotated tunnel URLs
and relaunched at 21:52; their runner had been pushing turns since 21:45 into
a process that no longer existed. Those re-pushes were still queued when the
new handshake completed. Our duplicate guard keyed on `commit` discarded all
56 without touching belief or the scent field, which is exactly what it exists
for -- applying them would have played 56 phantom turns.

## The deadlock that preceded it, worth keeping

Both peers are at-least-once senders that re-push DIFFERENT messages: theirs
repeats the turn, ours repeats nothing and blocks on the agreements inbox.
`negotiate` is sent once per sub-game on both sides. So when we restarted to
take their new URLs, their one negotiate had already gone to the dead process,
their re-pushes went to a queue nothing was reading, and our handshake waited
on a greeting that would never be sent again. Neither implementation is wrong
about the spec; the combination cannot survive a restart. Fixed by them
restarting so their negotiate landed after our server was listening -- no code
change on either side.
