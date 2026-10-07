"""Speech model manager API (see app/speech_models.py)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from .. import speech_models
from ..transcribe.speech_helper import probe, shared_helper

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
async def list_models() -> dict:
    caps = await asyncio.to_thread(probe)
    return {
        "models": await asyncio.to_thread(speech_models.list_models, caps.get("apple_speech_asset_installed")),
        "helper": caps,
    }


@router.post("/{model_id:path}/install", status_code=202)
async def install_model(model_id: str) -> dict:
    if model_id not in speech_models.BY_ID:
        raise HTTPException(404, "unknown model")

    async def _run() -> None:
        await speech_models.install(model_id, helper=shared_helper())
        if model_id == speech_models.APPLE_SPEECH.id:
            probe(refresh=True)

    asyncio.create_task(_run(), name=f"install-{model_id}")
    return {"ok": True}


@router.delete("/{model_id:path}")
async def delete_model(model_id: str) -> dict:
    try:
        freed = await asyncio.to_thread(speech_models.delete, model_id)
    except KeyError:
        raise HTTPException(404, "unknown model")
    except speech_models.InUseError as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "freed_bytes": freed}
