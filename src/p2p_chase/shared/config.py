"""``ConfigManager`` — the only place this program learns a number from.

Three files, three jobs (book Appendix B, submission guidelines §7.2-7.3):

* ``game.toml``  — private and local: my port, my seed, my strategy, my model.
  Editable by hand, commented, never crosses the network, never signed.
* ``game.json``  — shared and signed: the constitution both peers hold
  byte-identically. Canonical JSON precisely because it must hash the same on
  two machines that may not even be running the same implementation.
* ``rate_limits.json`` — Gatekeeper budgets, versioned separately so they can be
  tightened during a league without touching game rules.

The shared file overlays the private one, so a peer cannot weaken an agreed term
by editing its own copy.
"""

import json
import tomllib
from pathlib import Path
from typing import Any

from p2p_chase.exceptions import ConfigError, ConfigVersionError
from p2p_chase.shared.overlay import deep_merge, translate_shared
from p2p_chase.shared.version import SUPPORTED_CONFIG_VERSIONS, SUPPORTED_SHARED_SCHEMAS

PRIVATE_FILE = "game.toml"
SHARED_FILE = "game.json"
RATES_FILE = "rate_limits.json"


class ConfigManager:
    """Loads, validates and serves configuration by dotted key."""

    def __init__(self, config_dir: str | Path) -> None:
        self.dir = Path(config_dir)
        if not self.dir.is_dir():
            raise ConfigError(
                f"Config directory not found: {self.dir}. Expected a folder holding "
                f"{PRIVATE_FILE}, {SHARED_FILE} and {RATES_FILE}."
            )
        self._values = _read_toml(self.dir / PRIVATE_FILE)
        _check_version(self._values, PRIVATE_FILE, SUPPORTED_CONFIG_VERSIONS)

        self._rates = _read_json(self.dir / RATES_FILE)
        _check_version(self._rates, RATES_FILE, SUPPORTED_CONFIG_VERSIONS)

        shared_path = self.dir / SHARED_FILE
        if not shared_path.is_file():
            raise ConfigError(
                f"Missing the shared, signed agreement file: {shared_path}. Both peers "
                "must hold a byte-identical copy before a match can start."
            )
        self.shared = _read_json(shared_path)
        _check_version(
            self.shared, SHARED_FILE, SUPPORTED_SHARED_SCHEMAS, key="schema_version"
        )
        deep_merge(self._values, translate_shared(self.shared))

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Fetch a value by dotted key, e.g. ``config.get("board.size")``."""
        node: Any = self._values
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def require(self, dotted_key: str) -> Any:
        """Fetch a value that has no sensible default, failing loudly if absent.

        Used for agreed terms: a missing board size must stop the process before
        a port is opened, not surface as a ``None`` crash on move seventeen.
        """
        value = self.get(dotted_key, _MISSING)
        if value is _MISSING:
            raise ConfigError(
                f"Required setting '{dotted_key}' is missing. Shared game terms must be "
                f"declared in {self.dir / SHARED_FILE}."
            )
        return value

    def override(self, dotted_key: str, value: Any) -> None:
        """Set a value at runtime (GUI controls, CLI flags). Creates missing sections."""
        parts = dotted_key.split(".")
        node = self._values
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def section(self, name: str) -> dict:
        """A whole configuration block as a plain dict (empty if absent)."""
        block = self.get(name, {})
        return dict(block) if isinstance(block, dict) else {}

    @property
    def rate_limits(self) -> dict:
        return self._rates

    def service_limits(self, service: str) -> dict:
        """Gatekeeper budgets for a service, falling back to the ``default`` block."""
        services = self._rates.get("rate_limits", {}).get("services", {})
        merged = dict(services.get("default", {}))
        merged.update(services.get(service, {}))
        return merged


_MISSING = object()


def _read_toml(path: Path) -> dict:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"Missing config file: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Missing config file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc


def _check_version(
    data: dict, source: str, supported: frozenset[str], key: str = "version"
) -> None:
    version = str(data.get(key, "unknown"))
    if version not in supported:
        raise ConfigVersionError(
            f"{source} declares {key}={version!r}, which this build does not support. "
            f"Supported: {sorted(supported)}."
        )
