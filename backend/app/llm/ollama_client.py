from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger(__name__)


def render(template: str, vars: dict[str, str]) -> str:
    out = template
    for k, v in vars.items():
        out = out.replace("{{" + k + "}}", v)
    return out


class OllamaClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=settings.ollama_host, timeout=120.0)
        self._resolved: str | None = None

    async def ping(self) -> bool:
        try:
            r = await self._client.get("/api/tags", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False

    async def _resolve_model(self) -> str:
        """Use the configured model if installed; otherwise fall back to an installed one
        (preferring the same family) so AI works even when OLLAMA_MODEL isn't pulled —
        e.g. the packaged app defaults to llama3.1:8b-instruct, which the user may not have."""
        if self._resolved is not None:
            return self._resolved
        want = settings.ollama_model
        try:
            r = await self._client.get("/api/tags", timeout=5.0)
            names = [m.get("name", "") for m in r.json().get("models", []) if m.get("name")]
        except Exception:
            names = []
        if not names or want in names:
            self._resolved = want
            return want
        family = want.split(":")[0]
        local = [n for n in names if not n.endswith(":cloud")]
        same_family = [n for n in local if n.split(":")[0] == family]
        chosen = (same_family or local or names)[0]
        log.warning("ollama model %r not installed; using %r (run: ollama pull %s)", want, chosen, want)
        self._resolved = chosen
        return chosen

    async def generate(self, prompt: str, *, model: str | None = None) -> str:
        try:
            r = await self._client.post(
                "/api/generate",
                json={
                    "model": model or await self._resolve_model(),
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3},
                },
            )
            r.raise_for_status()
            data = r.json()
            return (data.get("response") or "").strip()
        except Exception:
            log.exception("ollama generate failed")
            return ""

    async def close(self) -> None:
        await self._client.aclose()
