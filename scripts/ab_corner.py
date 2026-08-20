"""A/B the corner-seal fix against a reproduction of the officer that beat us.

We lost a counted series to imreeyal 30-90. All three thief windows ended the
same way: our thief in the corner (6,0), two of their fourteen walls on (5,0)
and (6,1), rule-47 concession. The fix moved "how many walls would it take to
cage this cell" out of the positional tie-break, where it could never fire, and
into the safety ranking itself.

Testing that against our own officer proves nothing -- ours captured nothing in
five live windows and spent zero of fourteen walls. The comparison only means
something against an officer that *pinches*, which is what
:class:`PincherPolice` is for.

``LegacySafeThief`` below restores the pre-fix ranking. It lives here rather
than in ``src/`` deliberately: a measurement needs the old behaviour, the
shipped tree does not, and dead strategy in a graded repository is a liability.

    uv run python scripts/ab_corner.py --matches 200

What this shows and does not show: PincherPolice is our reconstruction of a
tactic inferred from six signed sub-games, not imreeyal's code. A win here is
evidence, not proof.
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import arena  # noqa: E402

from p2p_chase.constants import Outcome  # noqa: E402
from p2p_chase.strategy.safe_thief import SafeThief  # noqa: E402


class LegacySafeThief(SafeThief):
    """The thief exactly as it was when it lost, for one honest comparison.

    The only difference is the ranking tuple: no room term, so a corner and the
    open centre tie at the saturated ply count and the tie falls through to a
    positional score in which ``mobility_weight`` cannot outvote distance.
    """

    def _safety(self, table, target, threats, context):
        plies = [self._against(table, target, officer, context) for officer in threats]
        if not plies:
            return table.depth, 0, 0
        return min(plies), sum(1 for p in plies if p > 0), sum(plies)


def _run(cop_key: str, thief_cls, matches: int) -> dict:
    games = [arena.play(arena.BRAINS[cop_key], thief_cls, seed) for seed in range(matches)]
    captures = [g for g in games if g["result"] == Outcome.CAPTURE.value]
    enclosures = [g for g in captures if g["how"] in ("enclosure", "sealed on the thief")]
    return {
        "matches": len(games),
        "capture_rate": round(len(captures) / len(games), 3),
        "sealed_in": len(enclosures),
        "mean_steps": round(statistics.fmean(g["steps"] for g in games), 1),
        "mean_barriers": round(statistics.fmean(g["barriers"] for g in games), 2),
        "thief_points": sum(5 if g["result"] == "capture" else 10 for g in games),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--matches", type=int, default=200)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    thieves = {"legacy (lost 30-90)": LegacySafeThief, "current (fixed)": SafeThief}
    report = {
        cop: {name: _run(cop, cls, args.matches) for name, cls in thieves.items()}
        for cop in ("pincher", "architect")
    }
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    for cop, rows in report.items():
        print(f"\nvs {cop}")
        print(f"  {'thief':<22}{'capture':>9}{'sealed':>8}{'steps':>8}{'walls':>8}{'points':>8}")
        for name, row in rows.items():
            print(
                f"  {name:<22}{row['capture_rate']:>9}{row['sealed_in']:>8}"
                f"{row['mean_steps']:>8}{row['mean_barriers']:>8}{row['thief_points']:>8}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
