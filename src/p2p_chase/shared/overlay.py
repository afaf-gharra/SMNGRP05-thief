"""Map the shared, signed ``game.json`` onto this build's internal namespace.

The shared file's shape is fixed by the book (Appendix B/F) and by every other
team's implementation — we do not get to rename its keys. Internally we prefer a
flatter, dotted namespace. This module is the single, explicit boundary between
the two, so the rest of the package never has to know what the wire format calls
things.

Only keys actually present are emitted, so a partially-specified agreement
overlays cleanly on top of the local defaults instead of blanking them.
"""

from typing import Any

#: (shared JSON section, key) -> internal dotted key.
_MAPPING: dict[tuple[str, str], str] = {
    ("board_and_agents", "grid_size"): "board.size",
    ("board_and_agents", "num_agents"): "board.num_agents",
    ("board_and_agents", "thief_start"): "positions.thief_start",
    ("board_and_agents", "cop_start"): "positions.cop_start",
    ("board_and_agents", "axis_origin_corner"): "board.axis_origin_corner",
    ("board_and_agents", "axis_start_index"): "board.axis_start_index",
    ("world", "map_area"): "play.setting",
    ("world", "hint_max_words"): "play.hint_max_words",
    ("movement_and_barriers", "move_set"): "rules.move_set",
    ("movement_and_barriers", "max_barriers"): "rules.barriers_max",
    ("movement_and_barriers", "max_moves"): "rules.max_moves",
    ("movement_and_barriers", "survival_threshold"): "rules.survival_threshold",
    ("pheromones", "pheromone_center_intensity"): "smell.emit_intensity",
    ("pheromones", "pheromone_decay"): "smell.decay_per_step",
    ("pheromones", "pheromone_grid_size"): "smell.grid_size",
    ("pheromones", "pheromone_min_center_intensity"): "smell.min_center_intensity",
    ("pheromones", "pheromone_falloff"): "smell.falloff",
    ("network_and_league", "num_games"): "league.num_games",
    ("network_and_league", "diversity_reward"): "league.diversity_reward",
    ("network_and_league", "min_games_to_pass"): "league.min_games_to_pass",
    ("network_and_league", "max_games_per_team"): "league.max_games_per_team",
    ("network_and_league", "token_budget_per_series"): "league.token_budget",
    ("network_and_league", "response_timeout_sec"): "network.response_timeout_seconds",
    ("network_and_league", "watchdog_timeout_sec"): "network.agreed_watchdog_seconds",
}


def translate_shared(shared: dict) -> dict:
    """Convert a shared ``game.json`` into nested overlay form."""
    out: dict[str, Any] = {}
    for (section, key), dotted in _MAPPING.items():
        block = shared.get(section)
        if isinstance(block, dict) and key in block:
            _put(out, dotted, block[key])
    if isinstance(shared.get("scoring"), dict):
        out["scoring"] = {
            k: v for k, v in shared["scoring"].items() if not k.startswith("_")
        }
    if isinstance(shared.get("rate_limiter_gatekeeper"), dict):
        out["gatekeeper"] = {
            k: v for k, v in shared["rate_limiter_gatekeeper"].items()
            if not k.startswith("_")
        }
    return out


def _put(tree: dict, dotted: str, value: Any) -> None:
    section, _, leaf = dotted.partition(".")
    tree.setdefault(section, {})[leaf] = value


def deep_merge(base: dict, overlay: dict) -> None:
    """Recursively merge ``overlay`` into ``base``; the overlay wins on leaves.

    The direction matters: the *signed* shared terms overlay the private local
    file, so a peer can never quietly weaken an agreed rule by editing its own
    TOML (book Appendix B).
    """
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
