"""Exception hierarchy.

One root (:class:`ChaseError`) so a caller can catch everything this package
raises without also swallowing unrelated failures, and narrow subclasses so the
orchestrator can tell a *protocol* problem (forfeit the match) from a *transport*
problem (retry) from a *configuration* problem (refuse to start at all).
"""


class ChaseError(Exception):
    """Base class for every error raised by this package."""


class ConfigError(ChaseError):
    """A config file is missing, malformed, or incomplete."""


class ConfigVersionError(ConfigError):
    """A config file declares a version this build does not support."""


class AgreementError(ChaseError):
    """The opponent's signed terms do not match ours, so no fair game is possible."""


class CryptoError(ChaseError):
    """A commit-reveal verification failed: revealed data does not hash to its commit.

    This is never recoverable and never ambiguous. Per the book's iron rule, the
    forging side takes a technical loss and scores zero.
    """


class TransportError(ChaseError):
    """The opponent could not be reached, or replied with something unusable."""


class PhaseError(ChaseError):
    """An illegal state-machine transition was attempted (mandatory rule 5)."""


class DeadlineExceeded(ChaseError):
    """A request outlived its deadline. A missed deadline is a failure, not patience."""


class RateLimited(ChaseError):
    """The Gatekeeper refused an outbound call to protect the account."""


class RestartSeries(ChaseError):
    """Control-channel signal: abandon this series and replay it from sub-game 1."""
