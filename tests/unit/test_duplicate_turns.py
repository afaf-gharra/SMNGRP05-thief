"""An at-least-once opponent must not be able to corrupt our state.

Teams that re-push a turn while waiting are legitimate senders, not attackers:
the reference implementation applies such a duplicate twice, so a faithful port
inherits a bug that only shows up against a retrying opponent — mid-game, with
nobody at fault and nothing in either log to blame.
"""

from p2p_chase.constants import Role
from p2p_chase.peer.runtime import PeerRuntime


class _SilentTransport:
    """A transport that never delivers anything; the runtime is driven by hand."""

    def poll_turn(self, _timeout):
        return None


def _runtime(config) -> PeerRuntime:
    return PeerRuntime(role=Role.POLICE, config=config, transport=_SilentTransport())


def test_first_sighting_of_a_commit_is_not_a_duplicate(config):
    runtime = _runtime(config)
    assert runtime._is_duplicate({"commit": "abc123"}) is False


def test_the_same_commit_arriving_again_is_dropped(config):
    runtime = _runtime(config)
    runtime._is_duplicate({"commit": "abc123"})
    assert runtime._is_duplicate({"commit": "abc123"}) is True
    assert runtime._is_duplicate({"commit": "abc123"}) is True


def test_distinct_commits_are_all_accepted(config):
    runtime = _runtime(config)
    assert [runtime._is_duplicate({"commit": c}) for c in ("a", "b", "c")] == [
        False,
        False,
        False,
    ]


def test_a_message_without_a_commit_is_never_treated_as_a_duplicate(config):
    """Refusing here would drop a malformed message silently; let validation speak."""
    runtime = _runtime(config)
    assert runtime._is_duplicate({}) is False
    assert runtime._is_duplicate({"commit": ""}) is False


def test_dropping_a_duplicate_emits_an_event_so_it_is_visible_in_the_log(config):
    seen: list[dict] = []
    runtime = PeerRuntime(
        role=Role.POLICE,
        config=config,
        transport=_SilentTransport(),
        listener=seen.append,
    )
    runtime._is_duplicate({"commit": "dup"})
    seen.clear()
    runtime._is_duplicate({"commit": "dup"})
    assert any(event.get("type") == "duplicate_dropped" for event in seen)


def test_a_duplicate_does_not_consume_the_opponents_deadline(config):
    """The clock belongs to the opponent's *turn*, not to its retry traffic."""
    runtime = _runtime(config)
    runtime._is_duplicate({"commit": "x"})

    deadline = runtime.deadlines.start("opponent_turn")
    before = deadline.remaining
    for _ in range(5):
        assert runtime._is_duplicate({"commit": "x"}) is True
    assert deadline.remaining <= before
    assert not deadline.expired
