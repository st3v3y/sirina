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

    async def ping(self) -> bool:
        try:
            r = await self._client.get("/api/tags", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False

    async def generate(self, prompt: str, *, model: str | None = None) -> str:
        try:
            r = await self._client.post(
                "/api/generate",
                json={
                    "model": model or settings.ollama_model,
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
