"""The model-backed hint writer — language only, never navigation.

What the model is given: a prose brief describing the sector to *claim*, the
setting's vocabulary, the opponent's last line, and the word cap. What the model
is never given: the move. By the time this runs the move is already chosen,
sealed and immutable, so a hallucinated direction cannot become an illegal
action — the worst a bad completion can do is produce a weak sentence.

Three defences make the model optional in practice as well as in principle:
``every_n_steps`` throttling, a hard per-step deadline, and a template fallback
on any failure. A match must never stall because a provider is slow, and the
league scores efficiency, so spending nothing is a legitimate strategy.
"""

import time

from p2p_chase.constants import Cell, Role
from p2p_chase.strategy.talk import landmarks as geo
from p2p_chase.strategy.talk.templates import TemplateTalker

_SYSTEM = (
    "You are an agent in a cops-and-robbers game played on a grid. "
    "You write ONE short line of in-character banter. Rules you must obey: "
    "reply with the sentence only, no quotes, no preamble, no coordinates, "
    "no numbers, at most {max_words} words. The line must hint that you are "
    "near {place} ({sector} part of {setting}). Never mention grids, cells or rows."
)


class LlmTalker:
    """Wraps a provider; degrades to :class:`TemplateTalker` whenever it must."""

    def __init__(
        self, provider, fallback: TemplateTalker, every_n_steps: int = 1,
        deadline_seconds: float = 20.0,
    ) -> None:
        self._provider = provider
        self._fallback = fallback
        self._every = max(1, int(every_n_steps))
        self._deadline = float(deadline_seconds)
        self.tokens_used = 0
        self.calls = 0
        self.failures = 0

    @property
    def provider_name(self) -> str:
        return getattr(self._provider, "name", "llm")

    @property
    def planner(self):
        """Share the fallback's credibility ledger: one identity, one reputation."""
        return self._fallback.planner

    def say(self, role: Role, context, target: Cell | None) -> tuple[str, str, str, str]:
        hint, intent, reason, _ = self._fallback.say(role, context, target)
        step = context.state.step_number
        if step % self._every != 0:
            return hint, intent, f"{reason}; template turn ({step} % {self._every})", ""

        sector = geo.cell_sector(self._fallback.board, target or context.state.position)
        claimed = sector if intent == "truth" else geo.opposite(sector)
        prompt = self._build_prompt(role, claimed, context)
        text = self._ask(prompt, context)
        if not text:
            self.failures += 1
            return hint, intent, f"{reason}; model unavailable, template used", prompt
        return self._clip(text), intent, f"{reason}; written by {self.provider_name}", prompt

    def _build_prompt(self, role: Role, sector: str, context) -> str:
        words = self._fallback.words_for(sector) or ["the old quarter"]
        system = _SYSTEM.format(
            max_words=self._fallback.max_words,
            place=words[0],
            sector=sector,
            setting=context.setting or "the city",
        )
        heard = (context.opponent_hint or "").strip() or "(they have said nothing)"
        return (
            f"{system}\n\n"
            f"You are the {role.value}. Turn {context.state.step_number}. "
            f"They last said: \"{heard}\"\n"
            f"Write your line:"
        )

    def _ask(self, prompt: str, context) -> str:
        """Call the provider under a hard deadline; never raise into the turn loop."""
        budget = context.deadline_seconds or self._deadline
        started = time.perf_counter()
        try:
            self.calls += 1
            text = self._provider.complete(prompt, timeout=budget)
        except Exception:  # noqa: BLE001 - any provider failure is a fallback, not a crash
            return ""
        if time.perf_counter() - started > budget:
            return ""  # arrived, but too late to be worth trusting the pacing to
        self.tokens_used += int(getattr(self._provider, "last_tokens", 0) or 0)
        return (text or "").strip().strip('"')

    def _clip(self, text: str) -> str:
        line = text.splitlines()[0].strip() if text else ""
        return self._fallback.clip(line) if line else self._fallback.vague()

    def observe_sent(self, step: int, hint: str, own_scent: dict[Cell, float]) -> None:
        self._fallback.observe_sent(step, hint, own_scent)

    def summary(self) -> dict:
        return {
            "provider": self.provider_name,
            "tokens": self.tokens_used,
            "calls": self.calls,
            "failures": self.failures,
            **self.planner.summary(),
        }
