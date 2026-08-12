"""The SDK facade: the one public door into the product."""

import json
import shutil
import threading
from pathlib import Path

import pytest

from p2p_chase.exceptions import ConfigError
from p2p_chase.sdk import ChaseSdk
from tests.conftest import REPO_ROOT, LoopbackTransport, sealed_log

# ------------------------------------------------------------------ preflight


def test_preflight_reports_what_a_match_would_use(sdk):
    report = sdk.preflight()
    assert report["group_id"] == "SMNGRP05"
    assert report["agreed_terms"]["board_size"] == 7
    assert report["hint_provider"] == "template"
    assert report["scent_model"]["worked_example"]["after_1_turn"] == pytest.approx(0.80)


def test_preflight_refuses_an_incomplete_agreement(sdk):
    path = sdk.config.dir / "game.json"
    shared = json.loads(path.read_text(encoding="utf-8"))
    del shared["board_and_agents"]["grid_size"]
    path.write_text(json.dumps(shared), encoding="utf-8")
    with pytest.raises(ConfigError, match="Incomplete agreement"):
        ChaseSdk(sdk.config.dir).preflight()


# ----------------------------------------------------------------- verify_log


def test_verify_passes_a_clean_log(sdk, tmp_path):
    verdict = sdk.verify_log(sealed_log(tmp_path))
    assert verdict["passed"] is True
    assert verdict["verified_steps"] == 3


def test_verify_names_the_tampered_step(sdk, tmp_path):
    verdict = sdk.verify_log(sealed_log(tmp_path, tamper=True))
    assert verdict["passed"] is False
    assert verdict["failed_steps"] == [2]


def test_load_log_round_trips(sdk, tmp_path):
    assert sdk.load_log(sealed_log(tmp_path))["game_id"] == "g"


# ---------------------------------------------------------------- play_series


def test_play_series_runs_a_match_and_writes_artifacts(tmp_path):
    """The whole product through its one public door, with email suppressed."""
    configs = {}
    for name, group in (("cop", "SMNGRP05"), ("thief", "rival-01")):
        directory = tmp_path / name
        shutil.copytree(REPO_ROOT / "config" / "police", directory)
        shared = json.loads((directory / "game.json").read_text(encoding="utf-8"))
        shared["movement_and_barriers"].update(survival_threshold=8, max_moves=8)
        shared["network_and_league"]["num_games"] = 1
        (directory / "game.json").write_text(json.dumps(shared), encoding="utf-8")
        instance = ChaseSdk(directory, workdir=tmp_path / name)
        instance.config.override("game.group_id", group)
        instance.config.override("network.turn_timeout_seconds", 20)
        configs[name] = instance

    left, right = LoopbackTransport.pair()
    results: dict = {}

    def play(key, role, transport):
        results[key] = configs[key].play_series(
            role, transport=transport, send_email=False
        )

    threads = [
        threading.Thread(target=play, args=("cop", "police", left), daemon=True),
        threading.Thread(target=play, args=("thief", "thief", right), daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    assert set(results) == {"cop", "thief"}
    assert results["cop"]["email"]["sent"] is False
    assert Path(results["cop"]["result_path"]).is_file()
    assert (
        results["cop"]["result"]["mutual_agreement"]["sha256"]
        == results["thief"]["result"]["mutual_agreement"]["sha256"]
    )
