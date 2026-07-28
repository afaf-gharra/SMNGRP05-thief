"""The four artifacts, the replay auditor, and the properties they must have."""

import json

import pytest

from p2p_chase.domain.crypto import CommitReveal
from p2p_chase.gui.replay_data import TAMPERED, VERIFIED, build_frames, summarise
from p2p_chase.report.artifacts import (
    build_config,
    build_declaration,
    build_log,
    build_result,
)
from p2p_chase.report.emit import mutual_signature
from p2p_chase.report.naming import (
    config_filename,
    declaration_filename,
    ended_at,
    group_block,
    log_filename,
    result_filename,
    signature,
)

IDENTITY = {
    "group_id": "uoh-ag12", "group_name": "UOH-AG12", "members": ["a", "b"],
    "repos": {"cop": "https://example.test/cop", "thief": "https://example.test/thief"},
    "mcp_servers": {"cop": "http://a/mcp", "thief": "http://b/mcp"},
    "llm_model": "template-zero-token",
    "spec": {"cpu_type": "x86", "cpu_cores": 8, "ram_gb": 16.0, "gpu_type": None},
}
OPPONENT = {**IDENTITY, "group_id": "rival-01", "group_name": "Rival"}


def sealed(step: int, **extra) -> dict:
    payload = {"step": step, "position": [1, 1], "move": "MOVE:N", "hint": "north",
               "intent": "truth", "state": "grid=7x7;self=[1, 1];barriers=[[2, 2]]", **extra}
    return {"payload": payload, **CommitReveal.seal(payload)}


def summary(**overrides) -> dict:
    base = {
        "sub_game_number": 1, "role": "police", "group_id": "uoh-ag12",
        "opponent_group_id": "rival-01", "result": "capture", "winner": "police",
        "steps": 12, "started_at": "2026-08-01T10:00:00+00:00", "duration_seconds": 30.0,
        "tokens_total": 0, "barriers_used": 3, "phase_trail": ["WAITING_FOR_OPPONENT"],
        "opponent_profile": {"trust": 0.3}, "talker": {"provider": "template"},
        "records": [sealed(0, github_commit="abc123"), sealed(1), sealed(2)],
        "audit": {"passed": True},
    }
    return {**base, **overrides}


# ---------------------------------------------------------------- filenames


def test_every_filename_is_derived_from_the_game_id():
    """Ten matches, forty files: a fixed name would silently overwrite a report."""
    assert declaration_filename("a-vs-b") == "declaration_a-vs-b.json"
    assert config_filename("a-vs-b", 3) == "config_a-vs-b_g03.json"
    assert log_filename("a-vs-b", 12) == "log_a-vs-b_g12.json"
    assert result_filename("a-vs-b") == "result_a-vs-b.json"


def test_ended_at_adds_the_duration():
    assert ended_at("2026-08-01T10:00:00+00:00", 90).startswith("2026-08-01T10:01:30")


def test_ended_at_echoes_an_unparsable_stamp():
    assert ended_at("not-a-time", 90) == "not-a-time"


def test_a_group_block_signs_everything_except_its_own_signature():
    block = group_block(IDENTITY)
    recomputed = signature({k: v for k, v in block.items() if k != "signature"})
    assert block["signature"] == recomputed


# -------------------------------------------------------------- declaration


def test_the_declaration_orders_groups_deterministically():
    """Both peers must emit identical group ordering or their reports differ."""
    args = {"game_id": "a-vs-b", "game_uid": "uid", "started_at": "t0", "ended": "t1",
            "num_sub_games": 6, "token_ceiling": 200000}
    mine = build_declaration(own=IDENTITY, opponent=OPPONENT, **args)
    theirs = build_declaration(own=OPPONENT, opponent=IDENTITY, **args)
    assert mine["groups"] == theirs["groups"]
    assert mine["declaration_sha256"] == theirs["declaration_sha256"]


def test_the_declaration_carries_the_six_hardware_fields():
    declaration = build_declaration(
        game_id="a-vs-b", game_uid="uid", started_at="t0", ended="t1",
        num_sub_games=1, token_ceiling=1, own=IDENTITY, opponent=OPPONENT,
    )
    spec = declaration["groups"]["group_1"]["hardware_spec"]
    assert set(spec) == {"cpu_type", "cpu_freq_mhz", "cpu_cores", "ram_gb",
                         "gpu_model", "vram_gb"}


def test_the_declaration_carries_no_role_because_roles_alternate():
    declaration = build_declaration(
        game_id="a-vs-b", game_uid="uid", started_at="t0", ended="t1",
        num_sub_games=6, token_ceiling=1, own=IDENTITY, opponent=OPPONENT,
    )
    assert "role" not in json.dumps(declaration["groups"])


# ------------------------------------------------------------------- config


def test_the_config_lock_covers_the_terms_and_not_the_wrapper():
    """Both peers stamp their own filename, so the hash must exclude it."""
    terms = {"board_and_agents": {"grid_size": 7}, "_note": "commentary"}
    first = build_config(shared_terms=terms, game_id="a-vs-b", game_uid="u", sub_game_number=1)
    second = build_config(shared_terms=terms, game_id="a-vs-b", game_uid="u", sub_game_number=9)
    assert first["config_sha256"] == second["config_sha256"]
    assert first["config_name"] != second["config_name"]


def test_the_config_lock_changes_when_a_term_changes():
    a = build_config(shared_terms={"x": 1}, game_id="g", game_uid="u", sub_game_number=1)
    b = build_config(shared_terms={"x": 2}, game_id="g", game_uid="u", sub_game_number=1)
    assert a["config_sha256"] != b["config_sha256"]


# ---------------------------------------------------------------------- log


def test_the_log_carries_every_sealed_record():
    log = build_log(summary=summary(), game_id="a-vs-b", game_uid="u")
    assert len(log["records"]) == 3
    assert log["summary"]["result"] == "capture"
    assert log["mutual_agreement"]["confirmed"] is True


def test_the_log_reports_a_failed_audit_honestly():
    log = build_log(summary=summary(audit={"passed": False}), game_id="g", game_uid="u")
    assert log["mutual_agreement"]["confirmed"] is False


# ------------------------------------------------------------------- result


def test_the_mutual_signature_ignores_asymmetric_facts():
    """Timestamps and per-peer token counts legitimately differ; the hash must not."""
    rows = [{"sub_game_number": 1, "roles": {"a": "police", "b": "thief"},
             "result": "capture", "winner_group": "a", "score": {"a": 20, "b": 5},
             "started_at": "t0", "tokens": {"a": 100}}]
    other = [{**rows[0], "started_at": "t9", "tokens": {"a": 0}}]
    aggregate = {"total_score": {"a": 20, "b": 5}}
    assert mutual_signature("g", aggregate, rows) == mutual_signature("g", aggregate, other)


def test_the_mutual_signature_changes_when_the_outcome_changes():
    base = [{"sub_game_number": 1, "roles": {"a": "police"}, "result": "capture",
             "winner_group": "a", "score": {"a": 20}}]
    flipped = [{**base[0], "result": "survival", "winner_group": "b"}]
    assert mutual_signature("g", {}, base) != mutual_signature("g", {}, flipped)


def test_the_result_is_confirmed_only_when_every_audit_passed():
    good = {"sub_game_number": 1, "audit": {"log_verified": True}}
    bad = {"sub_game_number": 2, "audit": {"log_verified": False}}
    clean = build_result(game_id="g", game_uid="u", group_ids=["a", "b"], sub_games=[good],
                         aggregate={}, mutual_sha256="x", token_totals={})
    dirty = build_result(game_id="g", game_uid="u", group_ids=["a", "b"],
                         sub_games=[good, bad], aggregate={}, mutual_sha256="x",
                         token_totals={})
    assert clean["mutual_agreement"]["confirmed"] is True
    assert dirty["mutual_agreement"]["confirmed"] is False


# ----------------------------------------------------------- replay auditor


def test_the_replay_verifies_an_untouched_log():
    frames = build_frames({"records": [sealed(0), sealed(1), sealed(2)]})
    assert len(frames) == 2               # step zero is a declaration, not a position
    assert all(frame.verified for frame in frames)
    assert summarise({}, frames)["status"] == VERIFIED


def test_the_replay_catches_a_single_altered_byte():
    """The property the whole submission rests on: history cannot be rewritten."""
    records = [sealed(1), sealed(2), sealed(3)]
    records[1]["payload"]["position"] = [5, 5]
    frames = build_frames({"records": records})
    assert frames[0].verified is True
    assert frames[1].verified is False
    assert frames[1].status == TAMPERED
    assert summarise({}, frames)["failed_steps"] == [2]


def test_one_bad_step_voids_the_whole_match():
    records = [sealed(i) for i in range(1, 6)]
    records[4]["commit"] = "0" * 64
    assert summarise({}, build_frames({"records": records}))["status"] == TAMPERED


def test_a_record_missing_its_nonce_is_treated_as_tampered():
    record = sealed(1)
    del record["nonce"]
    assert build_frames({"records": [record]})[0].verified is False


def test_barriers_are_recovered_from_the_sealed_state_string():
    frames = build_frames({"records": [sealed(1)]})
    assert frames[0].barriers == [[2, 2]]


def test_a_state_string_without_barriers_yields_none():
    record = sealed(1, state="grid=7x7;self=[1, 1]")
    assert build_frames({"records": [record]})[0].barriers == []


@pytest.mark.parametrize("records", [[], [sealed(0)]])
def test_a_log_with_no_playable_steps_is_vacuously_verified(records):
    assert summarise({}, build_frames({"records": records}))["status"] == VERIFIED
