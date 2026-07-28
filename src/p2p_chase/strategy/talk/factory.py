"""Build the talker the private config asks for.

The default is deliberately ``template``: zero tokens, no network, no key, and
no way for someone else's outage to cost us a match. Opting into a model is one
line of TOML, and even then the template stays underneath as the fallback — so
the worst case of enabling a model is that we quietly stop using it.
"""

import random

from p2p_chase.domain.board import Board
from p2p_chase.exceptions import ConfigError
from p2p_chase.strategy.talk.llm_talker import LlmTalker
from p2p_chase.strategy.talk.templates import TemplateTalker

TEMPLATE = "template"
CLAUDE_API = "claude_api"
OLLAMA = "ollama"
CLAUDE_CLI = "claude_cli"
PROVIDERS = (TEMPLATE, CLAUDE_API, OLLAMA, CLAUDE_CLI)


def resolve_talker(config, board: Board, rng: random.Random | None = None):
    """Construct the configured talker, wired to the Gatekeeper when it needs one."""
    talk = config.section("trash_talk")
    provider_name = str(talk.get("provider", TEMPLATE)).strip().lower()
    if provider_name not in PROVIDERS:
        raise ConfigError(
            f"Unknown trash_talk.provider {provider_name!r}; expected one of {list(PROVIDERS)}"
        )

    template = TemplateTalker(
        board=board,
        setting=config.get("play.setting", "") or "",
        max_words=config.get("play.hint_max_words", 15),
        lie_rate=float(talk.get("lie_rate", 0.45)),
        rng=rng or random.Random(config.get("play.seed")),
    )
    if provider_name == TEMPLATE:
        return template

    provider = _build_provider(provider_name, talk, config)
    return LlmTalker(
        provider=provider,
        fallback=template,
        every_n_steps=int(talk.get("every_n_steps", 1)),
        deadline_seconds=float(config.get("llm.step_deadline_seconds", 20)),
    )


def _build_provider(name: str, talk: dict, config):
    from p2p_chase.infra.llm_provider import (  # noqa: PLC0415 - optional dependencies
        ClaudeApiProvider,
        ClaudeCliProvider,
        GatedProvider,
        OllamaProvider,
    )
    from p2p_chase.shared.gatekeeper import ApiGatekeeper  # noqa: PLC0415

    model = talk.get("model")
    if name == CLAUDE_API:
        raw = ClaudeApiProvider(model=model or "claude-haiku-4-5-20251001")
        service = "anthropic"
    elif name == OLLAMA:
        raw = OllamaProvider(model=model or "llama3.2", url=talk.get("ollama_url"))
        service = "ollama"
    else:
        raw = ClaudeCliProvider(
            executable=config.get("llm.executable", "claude"), model=model
        )
        service = "anthropic"
    return GatedProvider(raw, ApiGatekeeper(config.service_limits(service), service=service))
