"""Build the exact dictionary of terms both peers sign.

This is the single most interoperability-sensitive function in the project. The
handshake compares the two dictionaries with ``==`` and hashes them with
canonical JSON, so the key names, the key *set*, and the value types must match
what every other team in the league produces — byte for byte. Adding a field
here, however sensible, would make our peer unable to shake hands with anyone.

Consequently: agreed *values* that this build extends beyond the common set
(such as the scent falloff shape) live in the shared JSON but deliberately stay
out of the signed term set, and are validated separately by
:func:`describe_scent_model`.
"""

from p2p_chase.exceptions import ConfigError
from p2p_chase.shared.config import ConfigManager

#: Terms with no safe default: absent means we must refuse to start.
REQUIRED: tuple[str, ...] = (
    "board_size", "smell_grid_size", "decay_per_step", "emit_intensity",
    "min_center_intensity", "max_steps", "barriers_max", "thief_start", "cop_start",
)


def terms_from_config(config: ConfigManager) -> dict:
    """The signed agreement: everything the two peers must match on."""
    return {
        "board_size": config.get("board.size"),
        "smell_grid_size": config.get("smell.grid_size"),
        "decay_per_step": config.get("smell.decay_per_step"),
        "emit_intensity": config.get("smell.emit_intensity"),
        "min_center_intensity": config.get("smell.min_center_intensity"),
        "max_steps": config.get("rules.survival_threshold"),
        "barriers_max": config.get("rules.barriers_max"),
        "setting": config.get("play.setting"),
        "hint_max_words": config.get("play.hint_max_words", 15),
        "axis_origin_corner": config.get("board.axis_origin_corner", "top-left"),
        "axis_start_index": config.get("board.axis_start_index", 0),
        "thief_start": config.get("positions.thief_start"),
        "cop_start": config.get("positions.cop_start"),
        "num_games": config.get("league.num_games", 1),
    }


def validate_agreement(config: ConfigManager) -> dict:
    """Fail before any port is opened if an agreed term is missing or nonsensical.

    Cheap checks, run once, in exchange for never debugging a mid-match crash
    caused by a ``None`` that should have been a board size.
    """
    terms = terms_from_config(config)
    missing = [name for name in REQUIRED if terms.get(name) is None]
    if missing:
        raise ConfigError(
            "Incomplete agreement — missing shared term(s): " + ", ".join(missing) + ". "
            "These belong in the signed game.json (board_and_agents / pheromones / "
            "movement_and_barriers)."
        )
    _check_ranges(terms)
    return terms


def _check_ranges(terms: dict) -> None:
    size = terms["board_size"]
    for name in ("thief_start", "cop_start"):
        cell = terms[name]
        if (
            not isinstance(cell, (list, tuple))
            or len(cell) != 2
            or not all(isinstance(v, int) and 0 <= v < size for v in cell)
        ):
            raise ConfigError(f"{name}={cell!r} is not a valid cell on a {size}x{size} board")
    if terms["thief_start"] == terms["cop_start"]:
        raise ConfigError("The thief and the officer cannot start on the same cell")
    if not 0.0 < terms["decay_per_step"] < 1.0:
        raise ConfigError(
            f"decay_per_step must be a fraction in (0, 1); got {terms['decay_per_step']!r}. "
            "It is a multiplicative rate, not an absolute amount subtracted per turn."
        )
    if not 0.0 < terms["emit_intensity"] <= 1.0:
        raise ConfigError(f"emit_intensity must be in (0, 1]; got {terms['emit_intensity']!r}")
    if terms["smell_grid_size"] % 2 == 0:
        raise ConfigError("smell_grid_size must be odd so the emitting cell has a centre")
    if terms["max_steps"] < 1 or terms["barriers_max"] < 0:
        raise ConfigError("max_steps must be positive and barriers_max non-negative")


def describe_scent_model(config: ConfigManager) -> dict:
    """The emission/decay model, spelled out with a worked example (rule 23).

    The book requires both teams to exchange the scent model *and a concrete
    numeric example* before a series, then lock the agreement cryptographically.
    A prose formula alone is exactly the kind of thing two implementations can
    read differently; one shared number is not.
    """
    peak = config.get("smell.emit_intensity")
    decay = config.get("smell.decay_per_step")
    return {
        "falloff": config.get("smell.falloff", "linear"),
        "grid_size": config.get("smell.grid_size"),
        "peak_intensity": peak,
        "decay_per_step": decay,
        "decay_formula": "tau(t+1) = max(0, (1 - rho) * tau(t) + delta_tau)",
        "worked_example": {
            "deposit": peak,
            "after_1_turn": round(peak * (1 - decay), 4),
            "after_7_turns": round(peak * (1 - decay) ** 7, 4),
        },
    }
