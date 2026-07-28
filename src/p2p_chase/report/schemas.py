"""Self-documenting descriptions embedded in each emitted artifact.

The lecturer receives four JSON files per match from every team, parsed by
machine. Carrying a plain-language ``_schema`` string inside each file means a
reader never has to find the right documentation to know what they are looking
at — the file explains itself, which is the whole reason the book specifies a
structured report rather than free text (mandatory rules 33-34).
"""

from typing import Final

SCHEMA_VERSION: Final[str] = "1.1"
DEFAULT_TIMEZONE: Final[str] = "Asia/Jerusalem"

DECLARATION: Final[str] = (
    "Pre-game declaration covering the WHOLE match (every sub-game) between two teams. "
    "This is the single home for everything that does not change while the sub-games are "
    "played: team identity, members, the cop and thief repository URLs, MCP server URLs, "
    "hardware specification, language model, the agreed token ceiling, and the match start "
    "and end times. Roles alternate across sub-games, so no role and no sub_game_number "
    "appear here. Both teams sign this and lock it cryptographically before play begins "
    "(book ch.5, step zero). Anything that varies per sub-game — the commit hash, the moves, "
    "the scores — lives in the log and result artifacts instead."
)

CONFIG: Final[str] = (
    "The agreed configuration for one sub-game. Every value traces to the binding parameter "
    "table in Appendix F. Both teams must hold byte-identical values, lock them "
    "cryptographically via config_sha256, give the file a name unique to the match, and "
    "attach it to the GitHub repository. Status recap: 'minimum' may only be raised by "
    "mutual agreement, 'permanent' must not change at all, 'negotiation' may take any "
    "agreed value."
)

LOG: Final[str] = (
    "Per-sub-game match log, consumed by the Replay Viewer for cryptographic audit. Each "
    "step is committed as SHA-256(state || move || intent || nonce) and revealed only at "
    "the final audit (book ch.5 commit-reveal, ch.7 replay). Static team metadata is not "
    "repeated here — it lives in the declaration and is joined by game_uid. Step 0 is the "
    "signed step-zero record carrying the hardware declaration and the exact commit hash "
    "that played. The prompt_discussion block records the natural-language exchange and the "
    "reasoning behind each hint, and is covered by the same hash as everything else."
)

RESULT: Final[str] = (
    "Final result for the WHOLE match (all sub-games) between two teams. It condenses the "
    "per-sub-game logs into a per-group score for each sub-game plus the aggregate the "
    "lecturer needs to build the league standings. Static team metadata is not repeated "
    "here — it lives in the declaration and is referenced by game_id and group_id. Both "
    "teams must agree on this result and each sends its own copy (book ch.9)."
)

LINKS: Final[str] = (
    "Logical roles, NOT fixed filenames. Every actual filename is derived from the game_id "
    "so files from different matches can never be confused. Match-level files (declaration, "
    "result) are named <role>_<game_id>.json; per-sub-game files (config, log) are named "
    "<role>_<game_id>_g<NN>.json where <NN> is the sub_game_number."
)
