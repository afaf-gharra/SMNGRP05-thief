"""The graded seam: how a peer decides where to move and what to say.

Two strictly separated responsibilities, and the separation is the design:

* **Spatial** — the move is chosen by deterministic Python that can guarantee
  legality. A language model is never consulted for it (mandatory rule 25).
* **Verbal** — the natural-language hint, which may deliberately mislead, and
  the analysis of the opponent's language. This is where a model earns its keep.
"""

from p2p_chase.strategy.base import BrainBase, Decision
from p2p_chase.strategy.factory import resolve_brain, resolve_brain_cls
from p2p_chase.strategy.police_brain import ArchitectPolice
from p2p_chase.strategy.thief_brain import OpenSpaceThief

__all__ = [
    "ArchitectPolice", "BrainBase", "Decision", "OpenSpaceThief",
    "resolve_brain", "resolve_brain_cls",
]
