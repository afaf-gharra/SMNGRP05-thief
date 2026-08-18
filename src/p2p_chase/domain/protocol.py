"""The peer-to-peer wire format.

These dataclasses are the *interoperability contract*: every team in the league
must exchange exactly these field names, so this module is deliberately the most
conservative in the package. Nothing here may grow a required field, because a
message carrying an unexpected key is rejected outright by peers built on the
course reference implementation.

The turn token travels **with** the turn message: receiving one is what makes it
your move. There is no separate "your turn now" signal to lose.
"""

from dataclasses import MISSING, asdict, dataclass, fields
from typing import Any


def _strict_from(cls, data: dict[str, Any]):
    """Build a message, requiring every mandatory field and ignoring unknown ones.

    Tolerating unknown keys is what lets a future revision add optional fields
    without breaking today's peers; demanding the mandatory ones is what stops a
    malformed message from silently becoming a legal-looking move.
    """
    known = {f.name for f in fields(cls)}
    required = {f.name for f in fields(cls) if f.default is MISSING}
    missing = required - data.keys()
    if missing:
        raise TypeError(f"{cls.__name__} missing required fields: {sorted(missing)}")
    return cls(**{key: value for key, value in data.items() if key in known})


@dataclass
class TurnMessage:
    """Everything one peer tells the other about its turn — and nothing more.

    The true position, move and intent are *not* here in the clear: they are
    sealed inside ``commit`` and proven only at the end-of-match audit. What does
    travel openly is exactly what the rules force into the open: the decaying
    scent field (unforgeable), any barrier placed (must be declared truthfully),
    capture claims and their honest answers, and free natural language that may
    be a lie.
    """

    step: int
    sender: str                          # "thief" | "police"
    hint: str                            # free natural language; may be untrue
    smell_grid: dict                     # {"r,c": intensity} — evidence, not coordinates
    commit: str                          # SHA-256(state|move|intent|nonce)
    timestamp: str                       # ISO-8601, one per move
    barrier_placed: list | None = None   # public declaration; impassable for both
    capture_claim: list | None = None    # police: "I claim you are on this cell"
    claim_response: dict | None = None   # honest {"claim": [r, c], "caught": bool}
    win_claim: dict | None = None        # thief: {"type": "survival"}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TurnMessage":
        return _strict_from(cls, data)


@dataclass
class ControlMessage:
    """Out-of-band coordination, deliberately outside the sealed game record.

    Pausing, restarting a series or quitting cleanly are operational concerns
    between two humans running two terminals. Keeping them off the commit chain
    means no operator convenience can ever be mistaken for a game action.
    """

    kind: str                            # "enable" | "status" | "restart" | "quit"
    sender: str
    sub_game_number: int = 1
    status: str = ""
    step_budget: float = 0.0
    payload: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ControlMessage":
        known = {f.name for f in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in known})


@dataclass
class AuditPayload:
    """End-of-match reveal: the full sealed history plus every nonce."""

    # These three fields and no others. The reference implementation builds this
    # with ``cls(**data)``, so an extra key does not get ignored -- it raises
    # TypeError and takes the opponent's process down at the audit, after a
    # complete and otherwise valid match. Adding a field here to explain
    # ourselves to a peer is therefore the one place where being helpful breaks
    # the game; say it in the report and in writing instead.
    sender: str
    records: list                        # [{"payload": {...}, "nonce": str, "commit": str}]
    result_claim: str                    # "capture" | "survival" | "timeout"

    #: End-of-series agreement digest. The one field allowed to join the three
    #: above, and only because it is *omitted* when unset: peers built on the
    #: reference do ``cls(**data)`` and would raise on a key they do not know,
    #: even one carrying null. Never set this during a sub-game -- it belongs to
    #: the separate series-consensus envelope, whose records list is empty.
    consensus_sha: str | None = None

    def to_dict(self) -> dict:
        message = asdict(self)
        if message["consensus_sha"] is None:
            del message["consensus_sha"]
        return message

    @classmethod
    def from_dict(cls, data: dict) -> "AuditPayload":
        return _strict_from(cls, data)
