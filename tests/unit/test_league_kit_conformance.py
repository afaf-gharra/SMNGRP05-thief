"""Our constructions against the league interop kit's own fixtures.

The kit exists because the opponent re-hashes our disclosed log at the end of
every match. Two implementations that are each perfectly correct, and serialise
JSON slightly differently, will each conclude the other forged its record — and
rule 35 scores that zero for *both* teams. It is the single most expensive way
to lose points in this league and it is invisible until you play someone.

We ran these fixtures once by hand against a clone in a temp directory, which
found two real defects: a homegrown ``game_uid`` derivation that agreed with
nobody, and a null in a numeric map that made the artifact checker refuse the
whole filing. A clone in a temp directory is not a regression test, and that
directory has already been wiped once, so the CORE vectors are vendored here
under ``tests/fixtures/league_kit`` with the upstream commit recorded beside
them.

Upstream: github.com/Imreec/copthief-league-protocol
"""

import hashlib
import json
import pathlib

import pytest

from p2p_chase.domain.crypto import CommitReveal, canonical_json, digest
from p2p_chase.domain.game_ids import derive_game_ids

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures" / "league_kit"


def _vectors(name: str) -> list[dict]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))["vectors"]


def test_the_pinned_upstream_commit_is_recorded():
    """So a future reader can diff these fixtures against the kit they came from."""
    commit = (FIXTURES / "KIT_COMMIT.txt").read_text(encoding="utf-8").strip()
    assert len(commit) == 40 and commit == commit.lower()


@pytest.mark.parametrize("case", _vectors("canonical_json"))
def test_our_canonical_form_matches_the_kit(case):
    """Sorted keys, compact separators, and ensure_ascii=False.

    The fixtures deliberately include an astral emoji, a Hebrew hint, a key sort
    that a UTF-16 runtime gets backwards, and a float at the exponent cliff --
    every one a real way two teams' bytes diverge.
    """
    produced = canonical_json(case["object"])
    assert produced == case["canonical"], case.get("note", "")
    assert hashlib.sha256(produced.encode("utf-8")).hexdigest() == case["sha256"]


@pytest.mark.parametrize("case", _vectors("commit_reveal"))
def test_our_commit_matches_the_kit(case):
    """A mismatch here is a false tamper_forfeit against an honest opponent."""
    assert CommitReveal.commit_of(case["payload"], case["nonce"]) == case["commit"], (
        case.get("note", "")
    )


@pytest.mark.parametrize("case", _vectors("game_uid"))
def test_our_terms_digest_is_the_hash_of_the_canonical_form(case):
    assert digest(case["terms"]) == hashlib.sha256(
        canonical_json(case["terms"]).encode("utf-8")
    ).hexdigest()


@pytest.mark.parametrize("case", _vectors("game_uid"))
def test_our_uid_derivation_matches_the_kit(case):
    """The defect the cross-team join caught: ours hashed {game_id, terms} and
    agreed with nobody. Each bundle was self-consistent, so no single-team test
    could ever have seen it."""
    _, uid = derive_game_ids(case["terms"], case["group_a"], case["group_b"])
    assert uid == case["game_uid"]


def test_the_uid_does_not_depend_on_which_side_derives_it():
    case = _vectors("game_uid")[0]
    assert derive_game_ids(case["terms"], case["group_a"], case["group_b"]) == derive_game_ids(
        case["terms"], case["group_b"], case["group_a"]
    )
