"""The greeting must name the group where the protocol says to look for it.

We shipped ``group_id`` nested inside ``identity`` and nowhere else. Four
opponents accepted that; the fifth refused the offer with "greeting missing
group_id (rule 5)" and their peer process died on the refusal, costing a
scheduled window.

They were right. A field the protocol requires of the *message* should not be
reachable only by knowing which sub-object we happened to file it in. It is now
a top-level sibling of terms/nonce/signature AND stays inside identity, because
peers already reading it from there must keep working.
"""

from p2p_chase.domain.negotiation import Negotiation

TERMS = {"board_size": 7, "max_steps": 35}
IDENTITY = {"group_id": "SMNGRP05", "members": ["Afaf Gharra", "Reem Awawdy"]}


def _signed(identity=IDENTITY, **context):
    return Negotiation(TERMS, identity=identity, context=context or None).signed()


def test_the_greeting_names_the_group_at_the_top_level():
    assert _signed()["group_id"] == "SMNGRP05"


def test_it_is_a_sibling_of_the_signature_not_a_child_of_identity():
    """Both places, deliberately — moving it would break peers reading the old one."""
    message = _signed()
    assert message["group_id"] == message["identity"]["group_id"]
    assert {"terms", "nonce", "signature", "group_id", "identity"} <= set(message)


def test_adding_it_did_not_disturb_the_signature():
    """The signature covers the terms alone, so no hash on either side moves."""
    from p2p_chase.domain.crypto import CommitReveal

    message = _signed()
    CommitReveal.verify(message["terms"], message["nonce"], message["signature"])


def test_an_identity_without_a_group_id_still_produces_the_key():
    """Empty is a value a validator can reject clearly; absent is one it cannot."""
    message = _signed(identity={"members": []})
    assert message["group_id"] == ""


def test_the_declared_guard_fields_still_ride_alongside():
    message = _signed(role="police", sub_game_number=3, game_uid="u")
    assert message["role"] == "police"
    assert message["sub_game_number"] == 3
    assert message["game_uid"] == "u"
    assert message["group_id"] == "SMNGRP05"
