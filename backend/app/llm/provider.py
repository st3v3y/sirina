"""One OpenAI-compatible LLM client for every provider.

Ollama, LM Studio, OpenAI, Google AI Studio, and Groq all speak the OpenAI API
(`POST {base_url}/chat/completions`, `GET {base_url}/models`), so a single
`OpenAICompatProvider` covers local and cloud — they differ only by base URL, whether
a key is required, and the model. The app talks to it through one seam: `generate(prompt) -> str`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from ..config import settings

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """The AI provider failed (down, timed out, rejected the request). Distinct from a
    legitimately empty completion so callers can surface it instead of saving ''."""


def render(template: str, vars: dict[str, str]) -> str:
    # Single pass over the template: a placeholder-looking string INSIDE a substituted
    # value (e.g. '{{question}}' quoted in a transcript) must not be re-expanded.
    return re.sub(
        r"\{\{(\w+)\}\}",
        lambda m: vars.get(m.group(1), m.group(0)),
        template,
    )


@dataclass(frozen=True)
class Preset:
    key: str
    label: str
    base_url: str
    requires_key: bool
    is_cloud: bool


# Provider presets. `custom` carries no base URL (the user supplies one) and is treated
# as cloud unless its URL is an obvious loopback address (see `is_local_provider`).
PRESETS: dict[str, Preset] = {
    "ollama": Preset("ollama", "Ollama (local)", "http://localhost:11434/v1", False, False),
    "lmstudio": Preset("lmstudio", "LM Studio (local)", "http://localhost:1234/v1", False, False),
    "openai": Preset("openai", "OpenAI", "https://api.openai.com/v1", True, True),
    "google": Preset(
        "google", "Google AI Studio",
        "https://generativelanguage.googleapis.com/v1beta/openai", True, True,
    ),
    "groq": Preset("groq", "Groq", "https://api.groq.com/openai/v1", True, True),
    "custom": Preset("custom", "Custom (OpenAI-compatible)", "", False, True),
}

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def is_loopback(url: str) -> bool:
    try:
        return (urlparse(url).hostname or "") in _LOOPBACK_HOSTS
    except Exception:
        return False


def effective_base_url(provider: str, base_url: str | None) -> str:
    """An explicit base_url wins; otherwise use the preset's."""
    if base_url:
        return base_url
    preset = PRESETS.get(provider)
    return preset.base_url if preset else ""


def is_local_provider(provider: str, base_url: str) -> bool:
    """Local providers (Ollama/LM Studio, or a custom loopback URL) get the installed-model
    fallback and need no key; cloud providers don't."""
    preset = PRESETS.get(provider)
    if preset is None or preset.key == "custom":
        return is_loopback(base_url)
    return not preset.is_cloud


class OpenAICompatProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        model: str = "",
        *,
        allow_fallback: bool = False,
        ollama_native: bool = False,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        # Local models can take minutes on a long transcript (one summary section per call);
        # allow 5 min of silence on the socket before giving up (connect stays quick).
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=httpx.Timeout(300.0, connect=10.0), headers=headers
        )
        # Substitute an installed model when the configured one is missing — local only.
        self._allow_fallback = allow_fallback
        # Ollama ignores the context window on its OpenAI-compatible endpoint, so for Ollama
        # we route generate() to the native /api/chat with options.num_ctx (see generate()).
        self._ollama_native = ollama_native
        self._root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        self._resolved: str | None = None

    async def ping(self) -> bool:
        try:
            r = await self._client.get("/models", timeout=5.0)
            return r.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        try:
            r = await self._client.get("/models", timeout=10.0)
            r.raise_for_status()
            return [m.get("id", "") for m in r.json().get("data", []) if m.get("id")]
        except Exception:
            return []

    async def _resolve_model(self) -> str:
        """The configured model, except for local providers where we fall back to an
        installed model if it isn't present. Cloud NEVER substitutes — silently switching
        a billed model is wrong; an invalid model surfaces as an API error instead."""
        if not self._allow_fallback:
            return self.model
        if self._resolved is not None:
            return self._resolved
        want = self.model
        names = await self.list_models()
        if not names or want in names:
            self._resolved = want
            return want
        family = want.split(":")[0]
        same_family = [n for n in names if n.split(":")[0] == family]
        chosen = (same_family or names)[0]
        log.warning("model %r not installed; using %r", want, chosen)
        self._resolved = chosen
        return chosen

    async def generate(self, prompt: str, *, model: str | None = None, system: str | None = None) -> str:
        """Run one completion. Raises LLMError on provider failure — callers decide
        whether that's fatal (interactive summarize/ask surface it to the user) or
        best-effort (the auto-summary after transcription just logs it)."""
        try:
            use = model or await self._resolve_model()
            messages: list[dict[str, str]] = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            if self._ollama_native:
                return await self._generate_ollama(use, messages)
            r = await self._client.post(
                "/chat/completions",
                json={
                    "model": use,
                    "messages": messages,
                    "temperature": 0.3,
                    "stream": False,
                },
            )
            r.raise_for_status()
            choices = r.json().get("choices") or []
            if not choices:
                return ""
            return (choices[0].get("message", {}).get("content") or "").strip()
        except LLMError:
            raise
        except httpx.HTTPStatusError as e:
            log.exception("llm generate failed (base_url=%s)", self.base_url)
            detail = ""
            try:
                detail = (e.response.text or "")[:200]
            except Exception:
                pass
            raise LLMError(f"AI provider returned {e.response.status_code}: {detail}") from e
        except Exception as e:
            log.exception("llm generate failed (base_url=%s)", self.base_url)
            raise LLMError(
                f"AI provider unreachable ({type(e).__name__}) — is it running? "
                f"(base_url={self.base_url})"
            ) from e

    async def _generate_ollama(self, model: str, messages: list[dict[str, str]]) -> str:
        """Ollama's native /api/chat, which honors options.num_ctx — unlike its
        OpenAI-compatible endpoint, which silently truncates to the server default."""
        body: dict = {"model": model, "messages": messages, "stream": False,
                      "options": {"temperature": 0.3},
                      # Thinking models otherwise reason for minutes before answering;
                      # models without thinking ignore the flag.
                      "think": bool(settings.llm_think)}
        ctx = settings.llm_context_tokens
        if ctx and ctx > 0:
            body["options"]["num_ctx"] = ctx
        r = await self._client.post(f"{self._root}/api/chat", json=body)
        r.raise_for_status()
        return (r.json().get("message", {}).get("content") or "").strip()

    async def close(self) -> None:
        await self._client.aclose()


def build_llm() -> OpenAICompatProvider:
    """Construct the active provider from settings (provider preset + overrides)."""
    provider = settings.llm_provider
    base_url = effective_base_url(provider, settings.llm_base_url)
    local = is_local_provider(provider, base_url)
    return OpenAICompatProvider(
        base_url, settings.llm_api_key, settings.llm_model,
        allow_fallback=local, ollama_native=(provider == "ollama"),
    )
