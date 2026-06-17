from fastapi import APIRouter
from pydantic import BaseModel

from ..config import settings
from ..runtime import runtime

router = APIRouter(prefix="/api", tags=["status"])


class StatusResponse(BaseModel):
    ollama_ok: bool
    whisper_loaded: bool
    model: str
    engine: str  # active transcription engine (e.g. "mlx" or "faster-whisper")
    diarization: bool  # enabled AND a token is configured (i.e. will actually run)


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    return StatusResponse(
        ollama_ok=await runtime.ollama_ok(),
        whisper_loaded=runtime.whisper_loaded(),
        model=settings.whisper_model,
        engine=getattr(runtime.whisper, "name", "unknown"),
        diarization=bool(runtime.diarizer and runtime.diarizer.is_available()),
    )
