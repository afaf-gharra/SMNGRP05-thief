"""Check every shipped ``game.json`` against Appendix F's binding table.

The book marks each quantitative parameter with a status (printed p.135):

* ``קבוע``      -- binding, may not be changed at all. Deviating **disqualifies
                   the group**.
* ``מינימום``   -- the example value is a floor. Both groups may agree to raise
                   it; lowering it below the floor is forbidden.
* ``משא ומתן``  -- settled entirely in negotiation; the printed value is only an
                   example.

We had a 150-line ceiling enforced mechanically and no check at all on these,
which is precisely the gap aviayeli found in their own repository on 27/08 --
``min_games_to_pass`` sat at 1 for ten days because nothing looked at it.

Two design points, both learned from their write-up:
* the table lives here, once, rather than as literals at each call site;
* every config is checked, not the one that happens to be loaded -- their
  deviation existed in three files.

Run: ``python tools/appendix_f_check.py``  (exit 1 on any deviation)
"""

import glob
import json
import os
import sys

#: Appendix F, tables 13-19. Value and the page it is printed on.
PERMANENT = {
    ("board_and_agents", "num_agents"): 2,
    ("movement_and_barriers", "move_set"): ["N", "S", "E", "W", "STAY"],
    ("pheromones", "pheromone_center_intensity"): 0.9,
    ("pheromones", "pheromone_decay"): 0.10,
    ("pheromones", "pheromone_grid_size"): 5,
    ("scoring", "capture_cop"): 20,
    ("scoring", "capture_thief"): 5,
    ("scoring", "survival_cop"): 5,
    ("scoring", "survival_thief"): 10,
    ("scoring", "tie_score"): 2,
    ("network_and_league", "num_games"): 6,
    ("network_and_league", "diversity_reward"): 10,
    ("network_and_league", "min_games_to_pass"): 2,
}

FLOORS = {
    ("board_and_agents", "grid_size"): 7,
    ("movement_and_barriers", "max_barriers"): 14,
    ("movement_and_barriers", "max_moves"): 35,
    ("movement_and_barriers", "survival_threshold"): 35,
    ("rate_limiter_gatekeeper", "requests_per_minute"): 30,
    ("rate_limiter_gatekeeper", "concurrent_requests"): 2,
    ("rate_limiter_gatekeeper", "retry_backoff_sec"): 5,
    ("rate_limiter_gatekeeper", "max_retries"): 3,
    ("rate_limiter_gatekeeper", "queue_depth"): 100,
}

#: A one-sub-game warm-up legitimately carries num_games = 1: that is the
#: book's own example on printed p.113. Each entry is disclosed in a README
#: beside the config and none was ever counted or filed.
WARMUP_EXEMPT = {("network_and_league", "num_games")}


def audit(roots):
    findings = []
    files = sorted(f for r in roots for f in glob.glob(os.path.join(r, "*", "game.json")))
    for path in files:
        warmup = os.path.basename(os.path.dirname(path)).endswith("-quick")
        with open(path, encoding="utf-8") as handle:
            terms = json.load(handle)
        for (section, key), want in PERMANENT.items():
            got = (terms.get(section) or {}).get(key, "<missing>")
            if got == want:
                continue
            if warmup and (section, key) in WARMUP_EXEMPT:
                continue
            findings.append((path, f"{section}.{key}", f"קבוע: want {want!r}, got {got!r}"))
        for (section, key), floor in FLOORS.items():
            got = (terms.get(section) or {}).get(key)
            if got is None:
                findings.append((path, f"{section}.{key}", "מינימום: missing"))
            elif got < floor:
                findings.append((path, f"{section}.{key}", f"מינימום: floor {floor}, got {got}"))
    return files, findings


def main():
    files, findings = audit(["config", "../SMNGRP05-thief/config"])
    print(f"game.json files checked : {len(files)}")
    print(f"values checked          : {len(files) * (len(PERMANENT) + len(FLOORS))}")
    print(f"deviations              : {len(findings)}")
    for path, field, why in findings:
        print(f"   {path}\n     {field}: {why}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
