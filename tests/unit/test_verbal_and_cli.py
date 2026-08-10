"""The verbal layer, the host declaration and the command line."""

import random

import pytest

from p2p_chase.cli import build_parser, main
from p2p_chase.constants import Role
from p2p_chase.domain.board import Board
from p2p_chase.exceptions import ConfigError, TransportError
from p2p_chase.infra.llm_provider import GatedProvider, OllamaProvider
from p2p_chase.shared.sysinfo import collect_spec
from p2p_chase.strategy.talk.factory import resolve_talker
from p2p_chase.strategy.talk.llm_talker import LlmTalker
from p2p_chase.strategy.talk.templates import TemplateTalker
from tests.conftest import sealed_log

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
