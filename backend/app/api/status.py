from fastapi import APIRouter
from pydantic import BaseModel

from ..config import settings
from ..processing.diarize import diarization_supported
from ..runtime import runtime

router = APIRouter(prefix="/api", tags=["status"])


class StatusResponse(BaseModel):
    llm_ok: bool  # active LLM provider reachable
    whisper_loaded: bool
    whisper_state: str  # loading | ready | failed
    whisper_error: str | None = None  # reason when failed (e.g. offline download)
    engine: str  # active transcription engine ("whisperkit" or "faster-whisper")
    configured_engine: str  # the engine the user selected (auto | whisperkit | faster-whisper)
    engine_note: str | None = None  # set when the choice fell back (e.g. WhisperKit unavailable)
    llm_provider: str  # active LLM provider key
    llm_model: str  # active LLM model
    diarization: bool  # bundled AND enabled AND a token is configured (will actually run)
    # Whether pyannote exists in this build at all. False in the default packaged app —
    # the UI uses this to say "not in this build" instead of "turn it on in Settings".
    diarization_supported: bool = True


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
        diarization_supported=diarization_supported(),
    )
