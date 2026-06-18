from fastapi import APIRouter
from pydantic import BaseModel

from ..config import settings
from ..runtime import runtime

router = APIRouter(prefix="/api", tags=["status"])


class StatusResponse(BaseModel):
    llm_ok: bool  # active LLM provider reachable
    whisper_loaded: bool
    engine: str  # active transcription engine (e.g. "mlx" or "faster-whisper")
    llm_provider: str  # active LLM provider key
    llm_model: str  # active LLM model
    diarization: bool  # enabled AND a token is configured (i.e. will actually run)


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    return StatusResponse(
        llm_ok=await runtime.llm_ok(),
        whisper_loaded=runtime.whisper_loaded(),
        engine=getattr(runtime.whisper, "name", "unknown"),
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        diarization=bool(runtime.diarizer and runtime.diarizer.is_available()),
    )
