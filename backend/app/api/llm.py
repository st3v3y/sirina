"""LLM provider discovery + connection testing.

The chosen provider/model/base_url/key are persisted through `app-settings`
(`PATCH /api/settings`); these endpoints only *probe* against a throwaway client so the
Settings UI can populate the model dropdown and verify a key before saving.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import settings
from ..llm.provider import PRESETS, OpenAICompatProvider, effective_base_url

router = APIRouter(prefix="/api/llm", tags=["llm"])


class ProviderInfo(BaseModel):
    key: str
    label: str
    base_url: str
    requires_key: bool
    is_cloud: bool


class ProbeRequest(BaseModel):
    provider: str
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None


def _client_for(req: ProbeRequest) -> OpenAICompatProvider:
    base_url = effective_base_url(req.provider, req.base_url)
    # Use the request's key, or fall back to the stored secret when probing the
    # already-saved provider (so Test works without re-typing the key).
    api_key = req.api_key
    if not api_key and req.provider == settings.llm_provider:
        api_key = settings.llm_api_key
    return OpenAICompatProvider(base_url, api_key or "", req.model or "")


@router.get("/providers", response_model=list[ProviderInfo])
def list_providers() -> list[ProviderInfo]:
    return [
        ProviderInfo(
            key=p.key, label=p.label, base_url=p.base_url,
            requires_key=p.requires_key, is_cloud=p.is_cloud,
        )
        for p in PRESETS.values()
    ]


@router.post("/models")
async def list_models(req: ProbeRequest) -> dict[str, list[str]]:
    client = _client_for(req)
    try:
        return {"models": await client.list_models()}
    finally:
        await client.close()


@router.post("/test")
async def test_connection(req: ProbeRequest) -> dict:
    client = _client_for(req)
    try:
        ok = await client.ping()
        models = await client.list_models() if ok else []
        detail = "Reachable." if ok else "Not reachable — check the base URL and API key."
        return {"ok": ok, "detail": detail, "models": models}
    finally:
        await client.close()
