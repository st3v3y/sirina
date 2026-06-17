from fastapi import APIRouter
from pydantic import BaseModel

from ..audio import system_capture
from ..audio.local import list_input_devices

router = APIRouter(prefix="/api/audio", tags=["audio"])


@router.get("/devices")
def get_devices() -> list[dict]:
    return list_input_devices()


class AudioCapabilities(BaseModel):
    native_system_audio: bool  # native ScreenCaptureKit capture available (desktop app)


@router.get("/capabilities", response_model=AudioCapabilities)
def get_capabilities() -> AudioCapabilities:
    return AudioCapabilities(native_system_audio=system_capture.native_available())
