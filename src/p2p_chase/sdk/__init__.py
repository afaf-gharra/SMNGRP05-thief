"""Public SDK surface — the single entry point for every consumer.

CLI, GUI and any third party import :class:`ChaseSdk`; no consumer reaches into
the internal packages directly (submission guidelines §4.1).
"""

from p2p_chase.sdk.sdk import ChaseSdk

__all__ = ["ChaseSdk"]
