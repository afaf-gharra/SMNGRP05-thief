"""Single source of truth for versions (submission guidelines §8.1).

Three numbers travel with every match and must not drift apart:

* ``CODE_VERSION`` — sealed into the step-zero record, so the audit proves which
  build actually played;
* ``SUPPORTED_CONFIG_VERSIONS`` — refuses a config written for a different build
  rather than misreading it;
* ``SCHEMA_VERSION`` — stamped on the four report artifacts.
"""

from typing import Final

CODE_VERSION: Final[str] = "1.00"

#: Private per-peer TOML and rate-limit JSON versions this build accepts.
SUPPORTED_CONFIG_VERSIONS: Final[frozenset[str]] = frozenset({"1.00"})

#: Shared, signed game.json schema versions this build accepts. 1.3 is the
#: schema the course reference emits, so a stock opponent's file loads cleanly.
SUPPORTED_SHARED_SCHEMAS: Final[frozenset[str]] = frozenset({"1.2", "1.3"})

#: Version stamped on declaration / config / log / result artifacts.
SCHEMA_VERSION: Final[str] = "1.1"
