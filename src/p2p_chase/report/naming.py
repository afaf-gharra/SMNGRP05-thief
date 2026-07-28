"""Filenames, links and signatures shared by the four artifacts.

Every filename is derived from ``game_id``. That is not tidiness: a team plays
up to ten matches, each producing four files, and a fixed name like
``result.json`` would silently overwrite the previous match's report or, worse,
be emailed as if it belonged to the wrong opponent.
"""

from datetime import datetime, timedelta

from p2p_chase.domain.crypto import digest
from p2p_chase.report.schemas import LINKS


def declaration_filename(game_id: str) -> str:
    return f"declaration_{game_id}.json"


def config_filename(game_id: str, sub_game_number: int) -> str:
    return f"config_{game_id}_g{sub_game_number:02d}.json"


def log_filename(game_id: str, sub_game_number: int) -> str:
    return f"log_{game_id}_g{sub_game_number:02d}.json"


def result_filename(game_id: str) -> str:
    return f"result_{game_id}.json"


def links(game_id: str) -> dict:
    """The cross-reference block every artifact carries.

    Per-sub-game entries keep the literal ``g<NN>`` placeholder because the
    number varies between files that share this block.
    """
    return {
        "_remark": LINKS,
        "declaration": declaration_filename(game_id),
        "config": f"config_{game_id}_g<NN>.json",
        "log": f"log_{game_id}_g<NN>.json",
        "result": result_filename(game_id),
    }


def signature(payload) -> str:
    """SHA-256 over the canonical form — the lock referenced throughout the book."""
    return digest(payload)


def ended_at(started_at: str, duration_seconds: float) -> str:
    """``started_at + duration`` as ISO-8601, echoing the input if it will not parse."""
    try:
        start = datetime.fromisoformat(started_at)
    except (TypeError, ValueError):
        return started_at
    return (start + timedelta(seconds=duration_seconds)).isoformat()


def hardware_block(spec: dict) -> dict:
    """The six hardware fields the book's declaration asks for, and no others."""
    spec = spec or {}
    return {
        "cpu_type": spec.get("cpu_type"),
        "cpu_freq_mhz": spec.get("cpu_freq_mhz"),
        "cpu_cores": spec.get("cpu_cores"),
        "ram_gb": spec.get("ram_gb"),
        "gpu_model": spec.get("gpu_type"),
        "vram_gb": spec.get("vram_gb"),
    }


def group_block(identity: dict) -> dict:
    """One team's static block, signed over everything but the signature itself."""
    identity = identity or {}
    block = {
        "group_id": identity.get("group_id", "unknown-group"),
        "group_name": identity.get("group_name", "unnamed"),
        "members": identity.get("members", []),
        "repos": identity.get("repos", {}),
        "mcp_servers": identity.get("mcp_servers", {}),
        "llm_model": identity.get("llm_model", "template-zero-token"),
        "hardware_spec": hardware_block(identity.get("spec", {})),
    }
    block["signature"] = signature(block)
    return block
