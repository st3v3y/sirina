from fastapi import APIRouter
from pydantic import BaseModel

from ..config import settings
from ..runtime import runtime

router = APIRouter(prefix="/api", tags=["status"])


class StatusResponse(BaseModel):
    bot_connected: bool
    voice_channel: str | None
    ollama_ok: bool
    whisper_loaded: bool
    model: str


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    return StatusResponse(
        bot_connected=runtime.bot_connected(),
        voice_channel=runtime.voice_channel_name(),
        ollama_ok=await runtime.ollama_ok(),
        whisper_loaded=runtime.whisper_loaded(),
        model=settings.whisper_model,
    )
