"""Configuration loading, the signed-terms contract, and its guard rails."""

import json

import pytest

from p2p_chase.exceptions import ConfigError, ConfigVersionError
from p2p_chase.shared.config import ConfigManager
from p2p_chase.shared.overlay import deep_merge, translate_shared
from p2p_chase.shared.terms import (
    REQUIRED,
    describe_scent_model,
    terms_from_config,
    validate_agreement,
)


def patch_shared(config_dir, **sections):
    path = config_dir / "game.json"
    shared = json.loads(path.read_text(encoding="utf-8"))
    for section, values in sections.items():
        shared.setdefault(section, {}).update(values)
    path.write_text(json.dumps(shared), encoding="utf-8")
    return ConfigManager(config_dir)


def test_dotted_lookup_reads_the_private_file(config):
    assert config.get("game.group_id") == "SMNGRP05"
    assert config.get("network.my_port") == 8802


def test_dotted_lookup_returns_the_default_when_absent(config):
    assert config.get("nope.not.here", "fallback") == "fallback"


def test_the_shared_file_overlays_the_private_one(config):
    """The signed agreement wins, so a peer cannot weaken a term in its own TOML."""
    assert config.get("board.size") == 7
    assert config.get("rules.barriers_max") == 14
    assert config.get("smell.decay_per_step") == 0.10


def test_require_raises_a_useful_error_for_a_missing_term(config):
    with pytest.raises(ConfigError, match="Required setting 'nope.missing'"):
        config.require("nope.missing")


def test_override_creates_intermediate_sections(config):
    config.override("brand.new.key", 7)
    assert config.get("brand.new.key") == 7


def test_a_missing_config_directory_is_reported_clearly(tmp_path):
    with pytest.raises(ConfigError, match="Config directory not found"):
        ConfigManager(tmp_path / "nowhere")


def test_a_missing_shared_agreement_refuses_to_load(config_dir):
    (config_dir / "game.json").unlink()
    with pytest.raises(ConfigError, match="byte-identical copy"):
        ConfigManager(config_dir)


def test_an_unsupported_config_version_is_refused(config_dir):
    path = config_dir / "game.toml"
    path.write_text(path.read_text(encoding="utf-8").replace('version = "1.00"', 'version = "9.99"'),
                    encoding="utf-8")
    with pytest.raises(ConfigVersionError, match="9.99"):
        ConfigManager(config_dir)


def test_invalid_json_is_reported_with_the_filename(config_dir):
    (config_dir / "rate_limits.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid JSON"):
        ConfigManager(config_dir)


def test_service_limits_merge_over_the_default_block(config):
    gmail = config.service_limits("gmail")
    assert gmail["requests_per_minute"] == 6
    assert "queue_depth" in gmail


def test_unknown_services_fall_back_to_the_default_block(config):
    assert config.service_limits("nope")["requests_per_minute"] == 30


# --------------------------------------------------------------------- terms


def test_the_signed_term_set_is_exactly_the_interoperable_one(config):
    """This key set is a wire contract: adding to it would break every handshake."""
    assert set(terms_from_config(config)) == {
        "board_size", "smell_grid_size", "decay_per_step", "emit_intensity",
        "min_center_intensity", "max_steps", "barriers_max", "setting",
        "hint_max_words", "axis_origin_corner", "axis_start_index",
        "thief_start", "cop_start", "num_games",
    }


def test_a_valid_agreement_passes(config):
    assert validate_agreement(config)["board_size"] == 7


def test_required_terms_are_all_present_in_a_shipped_config(config):
    terms = terms_from_config(config)
    assert all(terms.get(name) is not None for name in REQUIRED)


def test_both_agents_starting_on_one_cell_is_refused(config_dir):
    config = patch_shared(config_dir, board_and_agents={"thief_start": [0, 0]})
    with pytest.raises(ConfigError, match="cannot start on the same cell"):
        validate_agreement(config)


def test_a_start_off_the_board_is_refused(config_dir):
    config = patch_shared(config_dir, board_and_agents={"thief_start": [99, 99]})
    with pytest.raises(ConfigError, match="not a valid cell"):
        validate_agreement(config)


def test_a_decay_outside_zero_to_one_is_refused(config_dir):
    """Guards the book-versus-code trap: decay is a rate, not an amount."""
    config = patch_shared(config_dir, pheromones={"pheromone_decay": 1.5})
    with pytest.raises(ConfigError, match="multiplicative rate"):
        validate_agreement(config)


def test_an_even_scent_window_is_refused(config_dir):
    config = patch_shared(config_dir, pheromones={"pheromone_grid_size": 4})
    with pytest.raises(ConfigError, match="must be odd"):
        validate_agreement(config)


def test_the_scent_model_ships_a_worked_numeric_example(config):
    """Rule 23: the model *and a concrete number* must be exchanged and locked."""
    model = describe_scent_model(config)
    assert model["peak_intensity"] == 0.9
    assert model["worked_example"]["after_1_turn"] == pytest.approx(0.81)
    assert model["worked_example"]["after_7_turns"] == pytest.approx(0.4305, abs=1e-3)


# ------------------------------------------------------------------- overlay


def test_translate_only_emits_keys_that_are_present():
    assert translate_shared({"board_and_agents": {"grid_size": 9}}) == {"board": {"size": 9}}


def test_translate_drops_commentary_keys():
    out = translate_shared({"scoring": {"capture_cop": 20, "_note": "ignore me"}})
    assert out["scoring"] == {"capture_cop": 20}


def test_deep_merge_replaces_leaves_and_keeps_siblings():
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    deep_merge(base, {"a": {"y": 99}})
    assert base == {"a": {"x": 1, "y": 99}, "b": 3}
