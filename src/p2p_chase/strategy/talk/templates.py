"""The zero-token hint writer.

The book is explicit that a strong agent needs no language model at all, and the
league rewards efficiency, so the default talker costs nothing: no API key, no
network, no rate limit, no way for a provider outage to stall a match. It still
produces *genuine* free natural language carrying a real spatial claim, which is
all the rules require.

Sentences are assembled rather than drawn from a fixed bank, so an opponent
cannot fingerprint us by our phrasing: a frame, a verb and a landmark from the
agreed setting combine into far more variants than a canned list, and every one
of them is parseable back into the sector it names.
"""

import random

from p2p_chase.constants import Cell, Intent, Role
from p2p_chase.domain.board import Board
from p2p_chase.strategy.talk import landmarks as geo
from p2p_chase.strategy.talk.bluff import BluffChoice, BluffPlanner, urgency_of

# Every frame here asserts presence, never absence. A negating frame such as
# "you will not find me anywhere near {place}" reads as a *denial* of the sector
# it is handed, so when the planner supplies the sector we actually want to
# suggest, the sentence says the opposite of what was intended -- and when it was
# handed our true sector under an honest intent flag, it put a plainly false
# statement into a signed record labelled truthful. Keep the claim and the flag
# pointing the same way.
#
# Every frame is also plain ASCII, deliberately. The hint travels inside the
# sealed payload, so an opponent that serialises with Python's default
# ``ensure_ascii=True`` renders one em-dash as ``—`` and computes a different
# digest for that step -- an honest turn that reads as tampering at the audit,
# where rule 35 voids the game for both teams. We cannot make other teams
# serialise correctly, but we can decline to hand them the opportunity. Two of
# these frames carried an em-dash and it reached three to eight sealed payloads
# per sub-game.
_THIEF_FRAMES = (
    "Slipping {prep} {place} while you waste time.",
    "Already {prep} {place}, and still moving.",
    "Catch your breath, I am {prep} {place}.",
    "Every alley {prep} {place} knows me better than you do.",
)
_POLICE_FRAMES = (
    "I am closing {prep} {place}; the doors are shutting.",
    "My people are {prep} {place}. Nowhere left to run.",
    "Working {prep} {place} now, and the walls are going up.",
    "I have {place} covered. Try me.",
    "Sweeping {prep} {place}, you left more of a trail than you think.",
)
_PREPOSITIONS = ("around", "through", "past", "near", "by")
_VAGUE = (
    "Still out here, still moving, still ahead of you.",
    "You talk a lot for someone who has found nothing.",
    "Keep guessing. The city is bigger than your patience.",
    "I have been in worse corners than this one.",
)


class TemplateTalker:
    """Assembles a hint from the agreed setting's vocabulary. Costs nothing."""

    provider_name = "template"

    def __init__(
        self, board: Board, setting: str, max_words: int = 15,
        lie_rate: float = 0.45, rng: random.Random | None = None,
    ) -> None:
        self._board = board
        self._setting = setting
        self._max_words = max(3, int(max_words))
        self._rng = rng or random.Random()
        self._gazetteer = geo.gazetteer_for(setting)
        self.planner = BluffPlanner(board, setting, lie_rate=lie_rate, rng=self._rng)
        self.planner.bind_landmarks(geo.landmark_index(board, setting))
        self.tokens_used = 0

    @property
    def board(self) -> Board:
        return self._board

    @property
    def max_words(self) -> int:
        return self._max_words

    def words_for(self, sector: str) -> list[str]:
        """The landmark vocabulary for a sector under the agreed setting."""
        return list(self._gazetteer.get(sector) or [])

    def say(self, role: Role, context, target: Cell | None) -> tuple[str, str, str, str]:
        """Return ``(hint, intent, reasoning, prompt)``. Prompt is empty: no model ran."""
        cell = target or context.state.position
        choice = self._plan(context, cell)
        hint = self._compose(role, choice)
        return hint, choice.intent, choice.reason, ""

    def _plan(self, context, cell: Cell) -> BluffChoice:
        true_sector = geo.cell_sector(self._board, cell)
        decoy = geo.opposite(true_sector)
        threat = context.belief.most_likely()
        urgency = urgency_of(
            steps_remaining=context.steps_remaining,
            total_steps=max(1, context.state.step_number + max(1, context.steps_remaining)),
            threat_distance=self._board.distance(cell, threat),
            board_size=self._board.size,
        )
        return self.planner.choose(true_sector, decoy, urgency, context.state.step_number)

    def _compose(self, role: Role, choice: BluffChoice) -> str:
        words = self._gazetteer.get(choice.sector) or []
        if not words:
            return self.clip(self._rng.choice(_VAGUE))
        frames = _THIEF_FRAMES if role is Role.THIEF else _POLICE_FRAMES
        sentence = self._rng.choice(frames).format(
            prep=self._rng.choice(_PREPOSITIONS), place=self._rng.choice(words)
        )
        return self.clip(sentence)

    def vague(self) -> str:
        """A hint that makes no falsifiable spatial claim."""
        return self.clip(self._rng.choice(_VAGUE))

    def clip(self, sentence: str) -> str:
        """Enforce the agreed word cap — it is a signed term, not a style preference."""
        words = sentence.split()
        if len(words) <= self._max_words:
            return sentence
        return " ".join(words[: self._max_words]).rstrip(",;:") + "."

    def observe_sent(self, step: int, hint: str, own_scent: dict[Cell, float]) -> None:
        self.planner.observe_own_hint(step, hint, own_scent)

    def summary(self) -> dict:
        return {"provider": self.provider_name, "tokens": self.tokens_used, **self.planner.summary()}


def default_intent() -> str:
    return Intent.TRUTH.value
