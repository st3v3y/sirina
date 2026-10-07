"""Ollama requests turn model "thinking" off unless the user enables it."""
import asyncio
import json

import httpx

from app.config import settings
from app.llm.provider import OpenAICompatProvider


def _provider(seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "ok"}})

    p = OpenAICompatProvider("http://ollama.test/v1", "", "qwen3.5:9b", ollama_native=True)
    p._client = httpx.AsyncClient(base_url=p.base_url, transport=httpx.MockTransport(handler))
    return p


def test_think_off_by_default(monkeypatch):
    seen = []
    monkeypatch.setattr(settings, "llm_think", False)
    out = asyncio.run(_provider(seen).generate("hi", model="qwen3.5:9b"))
    assert out == "ok" and seen[0]["think"] is False


def test_think_on_when_enabled(monkeypatch):
    seen = []
    monkeypatch.setattr(settings, "llm_think", True)
    asyncio.run(_provider(seen).generate("hi", model="qwen3.5:9b"))
    assert seen[0]["think"] is True


def test_timeout_allows_slow_local_models():
    p = OpenAICompatProvider("http://ollama.test/v1", "", "m", ollama_native=True)
    assert p._client.timeout.read == 300.0 and p._client.timeout.connect == 10.0
