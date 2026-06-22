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


@router.get("/capabilities", response_model=AudioCapabilities)
def get_capabilities() -> AudioCapabilities:
    return AudioCapabilities(native_system_audio=system_capture.native_available())
