"""Shared fixtures.

The important one is :class:`LoopbackTransport`: it implements exactly the same
five methods as :class:`~p2p_chase.infra.mcp_client.McpTransport`, so a complete
six-sub-game series can be played inside a unit test with no sockets, no ports
and no timing flakiness — while the code under test remains the code that plays
real matches.
"""

import json
import queue
import shutil
import threading
from pathlib import Path

import pytest

from p2p_chase.constants import Role
from p2p_chase.domain.board import Board
from p2p_chase.shared.config import ConfigManager

REPO_ROOT = Path(__file__).resolve().parents[1]


class LoopbackTransport:
    """One end of an in-memory peer pair."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.peer: LoopbackTransport | None = None
        self.agreements: queue.Queue = queue.Queue()
        self.turns: queue.Queue = queue.Queue()
        self.audits: queue.Queue = queue.Queue()
        self.controls: queue.Queue = queue.Queue()
        self.sent_turns: list[dict] = []

    @classmethod
    def pair(cls) -> tuple["LoopbackTransport", "LoopbackTransport"]:
        left, right = cls("left"), cls("right")
        left.peer, right.peer = right, left
        return left, right

    def exchange_agreement(self, signed: dict, expect_sub_game: int | None = None) -> dict:
        self.peer.agreements.put(signed)
        return self.agreements.get(timeout=10)

    def send_turn(self, message: dict) -> None:
        self.sent_turns.append(message)
        self.peer.turns.put(message)

    def poll_turn(self, timeout: float) -> dict | None:
        try:
            return self.turns.get(timeout=timeout)
        except queue.Empty:
            return None

    def send_control(self, message: dict) -> None:
        self.peer.controls.put(message)

    def poll_control(self) -> dict | None:
        try:
            return self.controls.get_nowait()
        except queue.Empty:
            return None

    def exchange_audit(self, payload: dict) -> dict | None:
        self.peer.audits.put(payload)
        try:
            return self.audits.get(timeout=10)
        except queue.Empty:
            return None

    def drain_inboxes(self) -> None:
        for inbox in (self.turns, self.audits, self.controls):
            while not inbox.empty():
                inbox.get_nowait()


@pytest.fixture
def board() -> Board:
    return Board(7)


@pytest.fixture
def sdk(tmp_path):
    """The SDK facade over a throwaway copy of the shipped police config."""
    from p2p_chase.sdk import ChaseSdk

    directory = tmp_path / "config"
    shutil.copytree(REPO_ROOT / "config" / "police", directory)
    return ChaseSdk(directory, workdir=tmp_path)


def sealed_log(tmp_path: Path, tamper: bool = False) -> Path:
    """A three-step commit-reveal log, optionally with one record rewritten."""
    from p2p_chase.domain.crypto import CommitReveal

    records = []
    for step in (1, 2, 3):
        payload = {"step": step, "position": [step, step], "move": "N"}
        records.append({"payload": payload, **CommitReveal.seal(payload)})
    if tamper:
        records[1]["payload"]["position"] = [9, 9]
    path = tmp_path / "log.json"
    path.write_text(json.dumps({"game_id": "g", "records": records}), encoding="utf-8")
    return path


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """A private copy of the police config, so a test may edit it freely."""
    target = tmp_path / "config"
    shutil.copytree(REPO_ROOT / "config" / "police", target)
    return target


@pytest.fixture
def config(config_dir: Path) -> ConfigManager:
    cfg = ConfigManager(config_dir)
    cfg.override("league.num_games", 1)
    cfg.override("network.turn_timeout_seconds", 10)
    cfg.override("paths.logs_dir", str(config_dir.parent / "logs"))
    return cfg


def make_config(config_dir: Path, **overrides) -> ConfigManager:
    """A config with the shared JSON patched — used to shorten matches in tests."""
    shared_path = config_dir / "game.json"
    shared = json.loads(shared_path.read_text(encoding="utf-8"))
    for dotted, value in overrides.items():
        section, _, key = dotted.partition(".")
        shared.setdefault(section, {})[key] = value
    shared_path.write_text(json.dumps(shared, indent=2), encoding="utf-8")
    return ConfigManager(config_dir)


def play_match(cop_config, thief_config, listener=None) -> tuple[dict, dict]:
    """Run one sub-game between two runtimes on a loopback pair, in two threads."""
    from p2p_chase.peer.runtime import PeerRuntime

    left, right = LoopbackTransport.pair()
    results: dict[str, dict] = {}

    def run(role: Role, cfg, transport) -> None:
        runtime = PeerRuntime(
            role=role, config=cfg, transport=transport, listener=listener
        )
        results[role.value] = runtime.run()

    threads = [
        threading.Thread(target=run, args=(Role.POLICE, cop_config, left), daemon=True),
        threading.Thread(target=run, args=(Role.THIEF, thief_config, right), daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=90)
    return results.get("police", {}), results.get("thief", {})
