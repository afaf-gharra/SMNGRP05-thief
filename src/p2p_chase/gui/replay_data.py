"""Turn a saved log into frames, verifying every step as it goes.

This is the headless half of the replay viewer, kept separate so it can be
tested exhaustively without a display — including the case that matters most,
a deliberately tampered log.

Each frame carries its own verdict. The viewer stamps the frame green only if
the commitment recorded during play still matches the revealed payload; a single
altered byte anywhere in the record changes the digest and the match is void
(mandatory rules 19-20). There is no "close enough": the comparison is binary
precisely so that no human judgement is involved.
"""

from dataclasses import dataclass, field

from p2p_chase.domain.crypto import CommitReveal
from p2p_chase.exceptions import CryptoError

VERIFIED = "Verified OK"
TAMPERED = "TAMPERED"


@dataclass
class Frame:
    """One replayable step and its cryptographic verdict."""

    step: int
    position: tuple[int, int]
    move: str
    hint: str
    intent: str
    barriers: list[list[int]] = field(default_factory=list)
    status: str = VERIFIED
    detail: str = ""

    @property
    def verified(self) -> bool:
        return self.status == VERIFIED


def _barriers_from_state(state: str) -> list[list[int]]:
    """Parse the ``barriers=[[r, c], ...]`` clause of a sealed state string."""
    marker = "barriers="
    if marker not in state:
        return []
    blob = state.split(marker, 1)[1]
    cells: list[list[int]] = []
    for chunk in blob.strip().strip("[]").split("], ["):
        parts = [part.strip(" []") for part in chunk.split(",")]
        if len(parts) == 2 and all(part.lstrip("-").isdigit() for part in parts):
            cells.append([int(parts[0]), int(parts[1])])
    return cells


def build_frames(log: dict) -> list[Frame]:
    """Verify and convert every record in a log into a renderable frame."""
    frames: list[Frame] = []
    for record in log.get("records", []):
        payload = record.get("payload", {})
        if payload.get("step") == 0:
            continue  # the step-zero declaration is not a board position
        frame = Frame(
            step=payload.get("step", len(frames) + 1),
            position=tuple(payload.get("position", (0, 0))),
            move=payload.get("move", "-"),
            hint=payload.get("hint", ""),
            intent=payload.get("intent", "truth"),
            barriers=_barriers_from_state(payload.get("state", "")),
        )
        try:
            CommitReveal.verify(payload, record["nonce"], record["commit"])
        except (CryptoError, KeyError, TypeError) as exc:
            frame.status = TAMPERED
            frame.detail = str(exc)
        frames.append(frame)
    return frames


def overall_status(frames: list[Frame]) -> str:
    """One failure anywhere voids the whole match — there is no partial credit."""
    return VERIFIED if all(frame.verified for frame in frames) else TAMPERED


def summarise(log: dict, frames: list[Frame]) -> dict:
    """Header information for the viewer and for ``p2p-chase verify``."""
    header = log.get("summary", {})
    failures = [frame.step for frame in frames if not frame.verified]
    return {
        "game_id": log.get("game_id"),
        "sub_game_number": header.get("sub_game_number"),
        "role": header.get("role"),
        "group_id": header.get("group_id"),
        "opponent_group_id": header.get("opponent_group_id"),
        "result": header.get("result"),
        "steps": len(frames),
        "status": overall_status(frames),
        "failed_steps": failures,
    }
