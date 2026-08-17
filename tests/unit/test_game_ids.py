"""Both peers must land on the same match name without asking each other.

The name is derived from the two group codes, sorted, so the order of who
dialled whom cannot change it. That is what stops two peers filing what looks
like two different matches — and under rule 35, a lecturer who receives only one
recognisable report scores nobody.

The derivation is also too rigid on its own. Two teams who warm up twice derive
the same name twice, so the second run silently overwrites the first one's
artifacts; we lost a match's logs to exactly that. And a peer that labels its
series separately reports a different fixture from ours. Hence the agreed-label
escape hatch, which is only ever a name both sides have settled in writing.
"""

from p2p_chase.domain.game_ids import derive_game_ids

TERMS = {"board_size": 7, "max_steps": 35, "thief_start": [3, 3], "cop_start": [0, 0]}


def test_the_name_does_not_depend_on_who_dialled_whom():
    ours = derive_game_ids(TERMS, "SMNGRP05", "uoh-ay26")
    theirs = derive_game_ids(TERMS, "uoh-ay26", "SMNGRP05")
    assert ours == theirs
    assert ours[0] == "SMNGRP05-vs-uoh-ay26"


def test_the_uid_binds_the_agreed_terms():
    """Same teams, different rules, distinguishable match."""
    _, first = derive_game_ids(TERMS, "SMNGRP05", "uoh-ay26")
    _, second = derive_game_ids({**TERMS, "max_steps": 40}, "SMNGRP05", "uoh-ay26")
    assert first != second


def test_the_uid_is_uuid_shaped():
    _, uid = derive_game_ids(TERMS, "SMNGRP05", "uoh-ay26")
    assert [len(part) for part in uid.split("-")] == [8, 4, 4, 4, 12]


def test_an_agreed_label_replaces_the_derived_name():
    label = "SMNGRP05-vs-uoh-ay26-W011"
    game_id, _ = derive_game_ids(TERMS, "SMNGRP05", "uoh-ay26", label)
    assert game_id == label


def test_an_agreed_label_still_lands_on_one_uid_from_either_side():
    """The label must not reintroduce the asymmetry the sorting removed."""
    label = "SMNGRP05-vs-uoh-ay26-W011"
    assert derive_game_ids(TERMS, "SMNGRP05", "uoh-ay26", label) == derive_game_ids(
        TERMS, "uoh-ay26", "SMNGRP05", label
    )


def test_relabelling_changes_the_uid_so_a_rerun_is_a_new_match():
    """The whole reason for the label: a second warm-up must not look like the
    first one resumed, and must not overwrite its artifacts."""
    _, first = derive_game_ids(TERMS, "SMNGRP05", "uoh-ay26")
    _, second = derive_game_ids(TERMS, "SMNGRP05", "uoh-ay26", "SMNGRP05-vs-uoh-ay26-W011")
    assert first != second


def test_no_label_keeps_the_derived_name():
    for empty in (None, ""):
        game_id, _ = derive_game_ids(TERMS, "SMNGRP05", "uoh-ay26", empty)
        assert game_id == "SMNGRP05-vs-uoh-ay26"


def test_an_agreed_uid_is_used_verbatim():
    """Deriving the uid only works if both peers derive it the same way.

    They do not. uoh-ay26 report one uid for two differently-named series against
    us, so theirs cannot depend on the match name while ours does. Until the
    league settles a single derivation, agreeing the string is the only reliable
    way to make two reports describe one match.
    """
    uid = "6d78d603-8930-4738-a68f-d5f79eec5ee1"
    assert derive_game_ids(TERMS, "SMNGRP05", "uoh-ay26", "W011", uid)[1] == uid


def test_an_agreed_uid_does_not_disturb_the_name():
    game_id, _ = derive_game_ids(TERMS, "SMNGRP05", "uoh-ay26", None, "fixed-uid")
    assert game_id == "SMNGRP05-vs-uoh-ay26"


def test_without_an_agreed_uid_nothing_changes():
    for empty in (None, ""):
        assert derive_game_ids(TERMS, "SMNGRP05", "uoh-ay26", None, empty) == derive_game_ids(
            TERMS, "SMNGRP05", "uoh-ay26"
        )
