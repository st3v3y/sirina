from fastapi import APIRouter
from pydantic import BaseModel

from ..config import settings
from ..runtime import runtime

router = APIRouter(prefix="/api", tags=["status"])


class StatusResponse(BaseModel):
    llm_ok: bool  # active LLM provider reachable
    whisper_loaded: bool
    whisper_state: str  # loading | ready | failed
    whisper_error: str | None = None  # reason when failed (e.g. offline download)
    engine: str  # active transcription engine (e.g. "mlx" or "faster-whisper")
    configured_engine: str  # the engine the user selected (auto | faster-whisper | mlx)
    engine_note: str | None = None  # set when the choice fell back (e.g. mlx unavailable)
    llm_provider: str  # active LLM provider key
    llm_model: str  # active LLM model
    diarization: bool  # enabled AND a token is configured (i.e. will actually run)


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    return StatusResponse(
        llm_ok=await runtime.llm_ok(),
        whisper_loaded=runtime.whisper_loaded(),
        whisper_state=runtime.whisper_state(),
        whisper_error=runtime.whisper_error,
        engine=getattr(runtime.whisper, "name", "unknown"),
        configured_engine=settings.transcription_engine or "auto",
        engine_note=runtime.engine_note,
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        diarization=bool(runtime.diarizer and runtime.diarizer.is_available()),
    )
