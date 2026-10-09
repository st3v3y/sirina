from fastapi import APIRouter
from pydantic import BaseModel

from ..audio import system_capture
from ..audio.local import list_input_devices
from ..runtime import runtime

router = APIRouter(prefix="/api/audio", tags=["audio"])


@router.get("/devices")
def get_devices(refresh: bool = False) -> list[dict]:
    # Re-enumerate PortAudio devices on demand (so a just-connected Bluetooth mic appears),
    # but never while recording — reinitializing PortAudio would tear down the live stream.
    recording = runtime.recorder is not None and runtime.recorder.is_recording()
    return list_input_devices(refresh=refresh and not recording)


class AudioCapabilities(BaseModel):
    native_system_audio: bool  # native system-audio helper available (desktop app)
    native_system_audio_reason: str | None = None  # why not, for the start dialog
    # Per-recording speech options for the start dialog: availability (+ why not) and
    # the Settings defaults.
    captions_available: bool = False
    captions_reason: str | None = None
    live_transcribe_available: bool = False
    live_transcribe_reason: str | None = None
    diarization_reason: str | None = None
    live_captions_default: bool = False
    live_transcribe_default: bool = False


@router.get("/capabilities", response_model=AudioCapabilities)
def get_capabilities() -> AudioCapabilities:
    from ..config import settings
    from ..processing.diarize import diarization_reason
    from ..recording.recorder import captions_reason, live_transcription_reason

    native_ok, native_reason = system_capture.native_available()
    captions_why = captions_reason()
    live_why = live_transcription_reason()
    return AudioCapabilities(
        native_system_audio=native_ok,
        native_system_audio_reason=native_reason,
        captions_available=captions_why is None,
        captions_reason=captions_why,
        live_transcribe_available=live_why is None,
        live_transcribe_reason=live_why,
        diarization_reason=diarization_reason(),
        live_captions_default=settings.live_captions_default,
        live_transcribe_default=settings.live_transcribe_default,
    )
