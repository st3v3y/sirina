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
    native_system_audio: bool  # native ScreenCaptureKit capture available (desktop app)
    # Per-recording speech options for the start dialog: availability + Settings defaults.
    captions_available: bool = False
    live_transcribe_available: bool = False
    live_captions_default: bool = False
    live_transcribe_default: bool = False


@router.get("/capabilities", response_model=AudioCapabilities)
def get_capabilities() -> AudioCapabilities:
    from ..config import settings
    from ..recording.recorder import captions_available, live_transcription_available

    return AudioCapabilities(
        native_system_audio=system_capture.native_available(),
        captions_available=captions_available(),
        live_transcribe_available=live_transcription_available(),
        live_captions_default=settings.live_captions_default,
        live_transcribe_default=settings.live_transcribe_default,
    )
