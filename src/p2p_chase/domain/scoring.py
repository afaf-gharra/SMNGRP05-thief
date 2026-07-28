"""League scoring: outcome -> points, and a whole series -> one agreed result.

Pure functions, no I/O, so the two peers compute byte-identical numbers from the
same facts and their two independently emailed reports agree. That agreement is
not a nicety: if the reports contradict, the book voids the match and scores both
teams zero (mandatory rule 35).

The point table is deliberately asymmetric (book table 2, Appendix F table 17):
capture pays the officer 20 and still pays the thief 5, while survival pays the
thief 10 and still pays the officer 5. Nobody walks away with nothing for
playing well, and a technical loss zeroes *both* sides — which is exactly the
incentive needed to stop anyone "winning" by hanging up the phone.
"""

from p2p_chase.constants import Outcome, Role

#: Fallbacks used only if a config omits the block; the agreed file normally wins.
DEFAULT_SCORING: dict[str, int] = {
    "capture_cop": 20,
    "capture_thief": 5,
    "survival_cop": 5,
    "survival_thief": 10,
    "tie_score": 2,
    "technical_loss": 0,
}


def score_subgame(result: str, roles: dict[str, str], scoring: dict) -> dict[str, int]:
    """Points each group earns from one sub-game.

    ``roles`` maps ``group_id -> role played this sub-game``, because roles
    alternate across the series and the group, not the role, is what accumulates
    a league score.
    """
    table = {**DEFAULT_SCORING, **(scoring or {})}
    points = dict.fromkeys(roles, table["technical_loss"])
    if result == Outcome.CAPTURE.value:
        for group, role in roles.items():
            points[group] = (
                table["capture_cop"] if role == Role.POLICE else table["capture_thief"]
            )
    elif result == Outcome.SURVIVAL.value:
        for group, role in roles.items():
            points[group] = (
                table["survival_cop"] if role == Role.POLICE else table["survival_thief"]
            )
    return points


def aggregate(subgame_scores: list[dict[str, int]], tie_score: int) -> dict:
    """Sum the sub-games into the series result, applying the book's tie rule.

    When the two totals are level the meeting is not left undecided: each group
    is credited ``tie_score`` so every fixture yields a scored outcome.
    """
    groups = sorted({group for scores in subgame_scores for group in scores})
    totals = {
        group: sum(scores.get(group, 0) for scores in subgame_scores) for group in groups
    }

    won = dict.fromkeys(groups, 0)
    ties = 0
    for scores in subgame_scores:
        if not scores:
            continue
        best = max(scores.values())
        leaders = [group for group, value in scores.items() if value == best]
        if len(leaders) == 1:
            won[leaders[0]] += 1
        else:
            ties += 1

    if len(groups) == 2 and totals[groups[0]] == totals[groups[1]]:
        for group in groups:
            totals[group] += tie_score
        return {
            "total_score": totals,
            "sub_games_won": won,
            "ties": ties,
            "winner_group": None,
            "series_tie": True,
        }

    return {
        "total_score": totals,
        "sub_games_won": won,
        "ties": ties,
        "winner_group": max(totals, key=lambda g: totals[g]) if totals else None,
        "series_tie": False,
    }
