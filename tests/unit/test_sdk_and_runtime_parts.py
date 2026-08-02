"""The SDK facade, the CLI, the reliability patterns and the verbal layer."""

import json
import random
import shutil
from pathlib import Path

import pytest

from p2p_chase.cli import build_parser, main
from p2p_chase.constants import Role
from p2p_chase.domain.board import Board
from p2p_chase.domain.crypto import CommitReveal
from p2p_chase.exceptions import ConfigError, TransportError
from p2p_chase.infra.llm_provider import GatedProvider, OllamaProvider
from p2p_chase.peer.deadline import Deadline, DeadlineTracker
from p2p_chase.peer.orchestrator import Orchestrator
from p2p_chase.peer.watchdog import Watchdog
from p2p_chase.sdk import ChaseSdk
from p2p_chase.shared.sysinfo import collect_spec
from p2p_chase.strategy.talk.factory import resolve_talker
from p2p_chase.strategy.talk.llm_talker import LlmTalker
from p2p_chase.strategy.talk.templates import TemplateTalker
from tests.conftest import LoopbackTransport

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def sdk(tmp_path) -> ChaseSdk:
    directory = tmp_path / "config"
    shutil.copytree(REPO_ROOT / "config" / "police", directory)
    return ChaseSdk(directory, workdir=tmp_path)


# ------------------------------------------------------------------ preflight


def test_preflight_reports_what_a_match_would_use(sdk):
    report = sdk.preflight()
    assert report["group_id"] == "SMNGRP05"
    assert report["agreed_terms"]["board_size"] == 7
    assert report["hint_provider"] == "template"
    assert report["scent_model"]["worked_example"]["after_1_turn"] == pytest.approx(0.81)


def test_preflight_refuses_an_incomplete_agreement(sdk):
    path = sdk.config.dir / "game.json"
    shared = json.loads(path.read_text(encoding="utf-8"))
    del shared["board_and_agents"]["grid_size"]
    path.write_text(json.dumps(shared), encoding="utf-8")
    with pytest.raises(ConfigError, match="Incomplete agreement"):
        ChaseSdk(sdk.config.dir).preflight()


# ----------------------------------------------------------------- verify_log


def sealed_log(tmp_path: Path, tamper: bool = False) -> Path:
    records = []
    for step in (1, 2, 3):
        payload = {"step": step, "position": [step, step], "move": "MOVE:N"}
        records.append({"payload": payload, **CommitReveal.seal(payload)})
    if tamper:
        records[1]["payload"]["position"] = [9, 9]
    path = tmp_path / "log.json"
    path.write_text(json.dumps({"game_id": "g", "records": records}), encoding="utf-8")
    return path


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


# ----------------------------------------------------------------- play_series


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
    import threading

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


# ------------------------------------------------------------------- deadline


def test_a_deadline_expires_and_is_counted():
    tracker = DeadlineTracker(default_budget=0.0)
    deadline = tracker.start("opponent_turn")
    assert deadline.expired is True
    assert tracker.record(deadline) is True
    assert tracker.summary()["total_expiries"] == 1


def test_a_met_deadline_is_counted_separately():
    tracker = DeadlineTracker(default_budget=60)
    deadline = tracker.start("opponent_turn")
    assert deadline.expired is False
    assert tracker.record(deadline) is False
    assert tracker.summary()["completions"] == {"opponent_turn": 1}


def test_resetting_a_deadline_restarts_the_budget():
    deadline = Deadline(budget_seconds=0.0)
    assert deadline.expired is True
    deadline.budget_seconds = 60
    deadline.reset()
    assert deadline.expired is False
    assert deadline.remaining > 0


# ------------------------------------------------------------------- watchdog


class Ticker:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_a_beating_loop_is_left_alone(tmp_path):
    clock = Ticker()
    dog = Watchdog(timeout_seconds=10, state_dir=tmp_path, clock=clock)
    clock.now = 5
    assert dog.check() is False
    dog.beat()
    clock.now = 12
    assert dog.check() is False
    assert dog.beats == 1


def test_a_frozen_loop_triggers_a_controlled_shutdown(tmp_path):
    clock = Ticker()
    fired: list[bool] = []
    dog = Watchdog(timeout_seconds=10, state_dir=tmp_path, clock=clock,
                   on_freeze=lambda: fired.append(True))
    dog.bind(lambda: {"phase": "COMPUTING_MOVE", "step": 7})
    clock.now = 30
    assert dog.check() is True
    assert fired == [True]
    saved = list(Path(tmp_path).glob("watchdog_*.json"))
    assert saved, "the watchdog must persist state so the match can still be reported"
    assert json.loads(saved[0].read_text(encoding="utf-8"))["step"] == 7


def test_the_watchdog_stays_triggered_once_it_fires(tmp_path):
    clock = Ticker()
    dog = Watchdog(timeout_seconds=1, state_dir=tmp_path, clock=clock)
    clock.now = 10
    dog.check()
    assert dog.check() is True
    assert dog.summary()["triggered"] is True


def test_a_failing_snapshot_does_not_mask_the_freeze(tmp_path):
    dog = Watchdog(timeout_seconds=1, state_dir=tmp_path, clock=Ticker())
    dog.bind(lambda: (_ for _ in ()).throw(RuntimeError("state is gone")))
    assert dog.persist() is None


def test_persist_without_a_snapshot_is_a_no_op(tmp_path):
    assert Watchdog(state_dir=tmp_path).persist() is None


def test_start_and_stop_are_idempotent(tmp_path):
    dog = Watchdog(timeout_seconds=60, state_dir=tmp_path, poll_seconds=0.01)
    dog.start()
    dog.start()
    dog.stop()
    dog.stop()


# --------------------------------------------------------------- orchestrator


def test_a_broken_transport_becomes_a_scored_technical_loss(sdk):
    """A crash must not lose the series: 0-0 is a result, silence is not."""

    class DeadTransport:
        def exchange_agreement(self, _signed):
            raise TransportError("opponent never came online")

        def drain_inboxes(self):
            pass

    sdk.config.override("league.num_games", 1)
    series = Orchestrator(sdk.config, DeadTransport()).play_series(Role.POLICE)
    assert len(series.summaries) == 1
    assert series.summaries[0]["result"] == "timeout"
    assert "opponent never came online" in series.summaries[0]["error"]


def test_the_orchestrator_snapshot_is_safe_before_a_sub_game(sdk):
    orchestrator = Orchestrator(sdk.config, object())
    assert "no sub-game" in orchestrator._snapshot()["status"]


# --------------------------------------------------------------- verbal layer


def test_the_default_talker_costs_nothing(sdk):
    talker = resolve_talker(sdk.config, Board(7), random.Random(1))
    assert isinstance(talker, TemplateTalker)
    assert talker.summary()["tokens"] == 0


def test_an_unknown_provider_is_refused(sdk):
    sdk.config.override("trash_talk.provider", "telepathy")
    with pytest.raises(ConfigError, match="Unknown trash_talk.provider"):
        resolve_talker(sdk.config, Board(7))


def test_opting_into_a_model_still_keeps_the_template_underneath(sdk):
    sdk.config.override("trash_talk.provider", "ollama")
    talker = resolve_talker(sdk.config, Board(7), random.Random(1))
    assert isinstance(talker, LlmTalker)
    assert talker.provider_name == "ollama"


def test_hints_obey_the_agreed_word_cap():
    talker = TemplateTalker(Board(7), "New York", max_words=4, rng=random.Random(3))
    assert len(talker.clip("one two three four five six").split()) == 4


def test_a_short_hint_is_left_alone():
    talker = TemplateTalker(Board(7), "New York", max_words=15, rng=random.Random(3))
    assert talker.clip("three short words") == "three short words"


def test_an_unknown_setting_falls_back_to_plain_bearings():
    talker = TemplateTalker(Board(7), "Atlantis", rng=random.Random(3))
    assert talker.words_for("N") == ["north", "top"]


def test_a_vague_line_makes_no_spatial_claim():
    talker = TemplateTalker(Board(7), "New York", rng=random.Random(3))
    assert talker.vague()


class FlakyProvider:
    name = "flaky"
    last_tokens = 0

    def complete(self, _prompt, timeout=20.0):
        raise TransportError("model is down")


def test_a_failed_model_falls_back_to_the_template_silently(sdk):
    """A provider outage must never stall a turn, let alone forfeit a match."""
    from p2p_chase.domain.belief import BeliefGrid
    from p2p_chase.domain.own_state import OwnGameState
    from p2p_chase.domain.trust import TrustEstimator
    from p2p_chase.strategy.base import TurnContext

    board = Board(7)
    template = TemplateTalker(board, "New York", rng=random.Random(1))
    talker = LlmTalker(FlakyProvider(), template)
    state = OwnGameState(Role.THIEF, (3, 3), 7, ["N", "S", "E", "W", "STAY"])
    context = TurnContext(state=state, belief=BeliefGrid(board),
                          trust=TrustEstimator(board_cells=49))
    hint, intent, reason, prompt = talker.say(Role.THIEF, context, (3, 3))
    assert hint
    assert intent in {"truth", "lie"}
    assert "model unavailable" in reason
    assert prompt  # the attempted prompt is still recorded for the audit trail
    assert talker.failures == 1


def test_the_gated_provider_routes_through_the_gatekeeper():
    calls: list[str] = []

    class Gate:
        def execute(self, call, *args, **kwargs):
            calls.append("gated")
            return call(*args, **kwargs)

    class Echo:
        name = "echo"
        last_tokens = 7

        def complete(self, prompt, timeout=20.0):
            return prompt.upper()

    provider = GatedProvider(Echo(), Gate())
    assert provider.complete("hi") == "HI"
    assert provider.name == "echo"
    assert provider.last_tokens == 7
    assert calls == ["gated"]


def test_ollama_reports_a_transport_error_rather_than_hanging():
    provider = OllamaProvider(url="http://127.0.0.1:1/api/generate")
    with pytest.raises(TransportError, match="Ollama call failed"):
        provider.complete("hello", timeout=0.5)


# -------------------------------------------------------------------- sysinfo


def test_the_host_spec_always_reports_the_book_fields():
    spec = collect_spec()
    assert {"os", "cpu_type", "cpu_cores", "ram_gb", "gpu_type", "vram_gb"} <= set(spec)
    assert spec["cpu_cores"] is None or spec["cpu_cores"] >= 1


# ------------------------------------------------------------------------ cli


def test_the_parser_exposes_every_command():
    parser = build_parser()
    for command in ("peer", "replay", "verify", "doctor"):
        assert parser.parse_args([command, *(["--role", "police"] if command in
                                             ("peer", "doctor") else
                                             ["--log", "x.json"])])


def test_no_command_prints_help_and_reports_misuse(capsys):
    assert main([]) == 2
    assert "usage" in capsys.readouterr().out


def test_doctor_reports_readiness(sdk, capsys):
    assert main(["doctor", "--config", str(sdk.config.dir)]) == 0
    assert "agreed_terms" in capsys.readouterr().out


def test_verify_exits_nonzero_on_a_tampered_log(sdk, tmp_path, capsys):
    path = sealed_log(tmp_path, tamper=True)
    assert main(["verify", "--config", str(sdk.config.dir), "--log", str(path)]) == 1
    assert "TAMPERED" in capsys.readouterr().out


def test_verify_exits_zero_on_a_clean_log(sdk, tmp_path, capsys):
    path = sealed_log(tmp_path)
    assert main(["verify", "--config", str(sdk.config.dir), "--log", str(path)]) == 0
    assert "Verified OK" in capsys.readouterr().out


def test_a_configuration_error_is_reported_not_raised(tmp_path, capsys):
    assert main(["doctor", "--config", str(tmp_path / "nowhere")]) == 1
    assert "ERROR" in capsys.readouterr().err
