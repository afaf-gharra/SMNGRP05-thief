"""End-to-end: two real peers, a real handshake, a real audit, real artifacts.

These drive the same code path a league match does — the orchestrator, the
runtime, the commit chain, the four artifacts — over an in-memory transport that
implements the identical five-method interface as the MCP one. What is *not*
mocked is everything that could actually be wrong.
"""

import json
import shutil
import threading
from pathlib import Path

import pytest

from p2p_chase.constants import Role
from p2p_chase.domain.crypto import audit_records
from p2p_chase.peer.orchestrator import Orchestrator, role_for
from p2p_chase.report.emit import emit_series
from p2p_chase.shared.config import ConfigManager
from tests.conftest import LoopbackTransport, make_config

REPO_ROOT = Path(__file__).resolve().parents[2]


def peer_config(tmp_path: Path, name: str, group_id: str, **shared) -> ConfigManager:
    directory = tmp_path / name
    shutil.copytree(REPO_ROOT / "config" / "police", directory)
    config = make_config(directory, **shared)
    config.override("game.group_id", group_id)
    config.override("game.group_name", group_id.upper())
    config.override("network.turn_timeout_seconds", 20)
    return config


def run_series(cop_config, thief_config) -> dict:
    """Play a whole series between two orchestrators on a loopback pair."""
    left, right = LoopbackTransport.pair()
    out: dict = {}
    errors: list[BaseException] = []

    def play(role: Role, config, transport) -> None:
        try:
            out[role.value] = Orchestrator(config, transport).play_series(role)
        except BaseException as exc:  # noqa: BLE001 - surfaced on the main thread
            errors.append(exc)

    threads = [
        threading.Thread(target=play, args=(Role.POLICE, cop_config, left), daemon=True),
        threading.Thread(target=play, args=(Role.THIEF, thief_config, right), daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=180)
    if errors:
        raise errors[0]
    assert set(out) == {"police", "thief"}, "a peer did not finish in time"
    return out


@pytest.fixture(scope="module")
def short_terms() -> dict:
    """A short match: the protocol is what is under test, not endurance."""
    return {
        "movement_and_barriers.survival_threshold": 12,
        "movement_and_barriers.max_moves": 12,
        "network_and_league.num_games": 2,
    }


@pytest.fixture(scope="module")
def played(tmp_path_factory, short_terms) -> dict:
    tmp_path = tmp_path_factory.mktemp("match")
    cop = peer_config(tmp_path, "cop", "uoh-ag12", **short_terms)
    thief = peer_config(tmp_path, "thief", "rival-01", **short_terms)
    series = run_series(cop, thief)
    results = {
        "cop_config": cop, "thief_config": thief, "tmp": tmp_path,
        "cop": series["police"], "thief": series["thief"],
    }
    results["cop_result"] = emit_series(cop, tmp_path / "logs", series["police"])
    results["thief_result"] = emit_series(thief, tmp_path / "logs", series["thief"])
    return results


@pytest.mark.slow
def test_both_peers_complete_every_sub_game(played):
    assert len(played["cop"].summaries) == 2
    assert len(played["thief"].summaries) == 2


@pytest.mark.slow
def test_the_two_peers_agree_on_the_match_identity(played):
    assert played["cop"].game_id == played["thief"].game_id
    assert played["cop"].game_uid == played["thief"].game_uid


@pytest.mark.slow
def test_roles_alternate_and_never_coincide(played):
    """When one peer is the officer the other must be the thief, every sub-game."""
    for cop_view, thief_view in zip(
        played["cop"].summaries, played["thief"].summaries, strict=True
    ):
        assert cop_view["role"] != thief_view["role"]


def test_role_alternation_is_symmetric_by_construction():
    for index in range(1, 7):
        assert role_for(Role.POLICE, index) is not role_for(Role.THIEF, index)


@pytest.mark.slow
def test_both_peers_reach_the_same_verdict(played):
    for cop_view, thief_view in zip(
        played["cop"].summaries, played["thief"].summaries, strict=True
    ):
        assert cop_view["result"] == thief_view["result"]
        assert cop_view["winner"] == thief_view["winner"]


@pytest.mark.slow
def test_every_commit_chain_verifies_end_to_end(played):
    for series in (played["cop"], played["thief"]):
        for view in series.summaries:
            assert audit_records(view["records"])["passed"] is True


@pytest.mark.slow
def test_the_mutual_audit_completed_on_both_sides(played):
    for series in (played["cop"], played["thief"]):
        for view in series.summaries:
            assert view["audit"]["passed"] is True
            assert view["audit"]["opponent_present"] is True
            assert view["audit"]["tampered_by"] is None


@pytest.mark.slow
def test_the_two_reports_agree_exactly(played):
    """Mandatory rule 35: contradicting reports void the match for both teams."""
    cop, thief = played["cop_result"], played["thief_result"]
    assert cop["game_id"] == thief["game_id"]
    assert cop["mutual_agreement"]["sha256"] == thief["mutual_agreement"]["sha256"]
    assert cop["final_result"]["total_score"] == thief["final_result"]["total_score"]
    assert cop["final_result"]["winner_group"] == thief["final_result"]["winner_group"]


@pytest.mark.slow
def test_each_peer_writes_all_four_artifacts(played):
    game_id = played["cop"].game_id
    for group in ("uoh-ag12", "rival-01"):
        directory = played["tmp"] / "logs" / group
        assert (directory / f"declaration_{game_id}.json").is_file()
        assert (directory / f"result_{game_id}.json").is_file()
        for number in (1, 2):
            assert (directory / f"config_{game_id}_g{number:02d}.json").is_file()
            assert (directory / f"log_{game_id}_g{number:02d}.json").is_file()


@pytest.mark.slow
def test_the_step_zero_record_seals_the_commit_that_played(played):
    """Mandatory rule 53: the examiner must be able to check out what ran."""
    first = played["cop"].summaries[0]["records"][0]["payload"]
    assert first["step"] == 0
    assert first["type"] == "system_spec"
    assert "github_commit" in first
    assert first["scent_model"]["decay_formula"].startswith("tau(t+1)")


@pytest.mark.slow
def test_no_position_is_ever_sent_in_the_clear(played):
    """The wire may carry evidence and claims, never a bare coordinate handout."""
    for message in played["cop"].summaries[0].get("move_log", []):
        assert "position" in message  # our *own* log may, of course
    turn_keys = {"step", "sender", "hint", "smell_grid", "commit", "timestamp",
                 "barrier_placed", "capture_claim", "claim_response", "win_claim"}
    from p2p_chase.domain.protocol import TurnMessage
    assert set(TurnMessage.__dataclass_fields__) == turn_keys


@pytest.mark.slow
def test_the_emitted_result_is_valid_json_on_disk(played):
    game_id = played["cop"].game_id
    path = played["tmp"] / "logs" / "uoh-ag12" / f"result_{game_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["report_type"] == "final_game_result"
    assert len(data["sub_games"]) == 2
