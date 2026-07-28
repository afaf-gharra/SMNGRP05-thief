"""Language-model providers behind one three-line interface.

    complete(prompt, timeout) -> str      # the text
    .last_tokens                          # what that cost
    .name                                 # what to write in the report

Three implementations, spanning the cost range the book lays out: a local model
(free, no rate limit), a small cloud model (cheap, metered), and the Claude Code
CLI (most expensive, but needs no key of its own). All three are optional — the
default talker uses none of them — and every one is imported lazily so a missing
dependency costs nothing until someone actually opts in.

Every provider is wrapped by :class:`~p2p_chase.shared.gatekeeper.ApiGatekeeper`
before it reaches the turn loop, so token accounting and rate limiting are not
each provider's problem.
"""

import json
import os
import subprocess
import urllib.error
import urllib.request

from p2p_chase.exceptions import TransportError

_MAX_OUTPUT_TOKENS = 60  # a taunt is one sentence; paying for more is waste


class ClaudeApiProvider:
    """A small Anthropic model over the official SDK."""

    name = "claude_api"

    def __init__(self, model: str = "claude-haiku-4-5-20251001", api_key: str | None = None):
        self.model = model
        self._key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = None
        self.last_tokens = 0

    def _ensure(self):
        if self._client is None:
            try:
                import anthropic  # noqa: PLC0415 - optional dependency
            except ImportError as exc:
                raise TransportError(
                    "provider='claude_api' needs the anthropic package: uv add anthropic"
                ) from exc
            if not self._key:
                raise TransportError("ANTHROPIC_API_KEY is not set (see .env-example)")
            self._client = anthropic.Anthropic(api_key=self._key)
        return self._client

    def complete(self, prompt: str, timeout: float = 20.0) -> str:
        client = self._ensure()
        response = client.messages.create(
            model=self.model,
            max_tokens=_MAX_OUTPUT_TOKENS,
            messages=[{"role": "user", "content": prompt}],
            timeout=timeout,
        )
        usage = getattr(response, "usage", None)
        self.last_tokens = (
            (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "output_tokens", 0) or 0)
        )
        parts = [block.text for block in response.content if getattr(block, "type", "") == "text"]
        return "".join(parts).strip()


class OllamaProvider:
    """A local model over Ollama's HTTP API: no key, no metering, no rate limit."""

    name = "ollama"

    def __init__(self, model: str = "llama3.2", url: str | None = None):
        self.model = model
        self.url = url or os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
        self.last_tokens = 0

    def complete(self, prompt: str, timeout: float = 20.0) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": _MAX_OUTPUT_TOKENS},
            }
        ).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310 - fixed localhost scheme from config
            self.url, data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise TransportError(f"Ollama call failed: {exc}") from exc
        self.last_tokens = int(payload.get("eval_count", 0) or 0) + int(
            payload.get("prompt_eval_count", 0) or 0
        )
        return str(payload.get("response", "")).strip()


class ClaudeCliProvider:
    """Reuse a local ``claude -p`` session. Highest cost, but needs no API key."""

    name = "claude_cli"

    def __init__(self, executable: str = "claude", model: str | None = None):
        self.executable = executable
        self.model = model
        self.last_tokens = 0

    def complete(self, prompt: str, timeout: float = 60.0) -> str:
        argv = [self.executable, "-p", "--output-format", "json"]
        if self.model:
            argv += ["--model", self.model]
        try:
            completed = subprocess.run(  # noqa: S603 - argv from config, no shell
                argv, input=prompt, capture_output=True, text=True, timeout=timeout, check=True
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise TransportError(f"claude CLI call failed: {exc}") from exc
        return self._parse(completed.stdout)

    def _parse(self, stdout: str) -> str:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return stdout.strip()
        usage = payload.get("usage") or {}
        self.last_tokens = int(usage.get("input_tokens", 0) or 0) + int(
            usage.get("output_tokens", 0) or 0
        )
        return str(payload.get("result", "")).strip()


class GatedProvider:
    """Routes any provider's calls through the Gatekeeper (guidelines §5.1)."""

    def __init__(self, provider, gatekeeper):
        self._provider = provider
        self._gatekeeper = gatekeeper

    @property
    def name(self) -> str:
        return self._provider.name

    @property
    def last_tokens(self) -> int:
        return self._provider.last_tokens

    def complete(self, prompt: str, timeout: float = 20.0) -> str:
        return self._gatekeeper.execute(self._provider.complete, prompt, timeout=timeout)
