"""Resolve which brain plays, from configuration.

The strategy is chosen by a ``"package.module:ClassName"`` selector in the
private TOML, so swapping in a new policy is a config change rather than a code
change — which is exactly what makes an A/B run between two strategies cheap
enough to actually do (see ``docs/RESEARCH-REPORT.md``).
"""

import importlib
import random

from p2p_chase.constants import Role
from p2p_chase.exceptions import ConfigError
from p2p_chase.strategy.base import BrainBase
from p2p_chase.strategy.police_brain import ArchitectPolice
from p2p_chase.strategy.thief_brain import OpenSpaceThief

_DEFAULTS: dict[Role, type[BrainBase]] = {
    Role.THIEF: OpenSpaceThief,
    Role.POLICE: ArchitectPolice,
}
_SELECTOR: dict[Role, str] = {
    Role.THIEF: "strategy.thief_class",
    Role.POLICE: "strategy.police_class",
}
_TUNING: dict[Role, str] = {
    Role.THIEF: "strategy.thief",
    Role.POLICE: "strategy.police",
}


def load_brain_cls(selector: str) -> type[BrainBase]:
    """Import a brain class from ``"package.module:ClassName"``."""
    module_path, separator, class_name = selector.partition(":")
    if not separator or not module_path or not class_name:
        raise ConfigError(
            f"Malformed strategy selector {selector!r}; expected 'package.module:ClassName'"
        )
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ConfigError(f"Cannot import strategy module {module_path!r}: {exc}") from exc
    try:
        candidate = getattr(module, class_name)
    except AttributeError as exc:
        raise ConfigError(f"{module_path!r} has no attribute {class_name!r}") from exc
    if not (isinstance(candidate, type) and issubclass(candidate, BrainBase)):
        raise ConfigError(f"{selector!r} is not a BrainBase subclass")
    return candidate


def resolve_brain_cls(config, role: Role) -> type[BrainBase]:
    """The brain class configured for ``role``, or the shipped default."""
    selector = config.get(_SELECTOR[role])
    return load_brain_cls(selector) if selector else _DEFAULTS[role]


def resolve_brain(config, role: Role, talker=None, rng: random.Random | None = None) -> BrainBase:
    """Instantiate the configured brain with its tuning block and talker."""
    brain_cls = resolve_brain_cls(config, role)
    tuning = config.section(_TUNING[role])
    return brain_cls(rng=rng or random.Random(config.get("play.seed")), talker=talker,
                     tuning=tuning)
