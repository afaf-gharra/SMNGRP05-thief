"""Distributed cops-and-robbers over a peer-to-peer network.

Two autonomous agents, no central server and no referee: fairness is produced by
SHA-256 commit-reveal, stigmergic scent trails and a Bayesian belief filter
rather than by anyone's good word.

Group uoh-ag12, University of Haifa, Department of Computer Science, 2026.
"""

from p2p_chase.shared.version import CODE_VERSION

__version__ = CODE_VERSION
__all__ = ["__version__"]
