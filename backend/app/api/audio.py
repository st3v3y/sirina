from fastapi import APIRouter

from ..audio.local import list_input_devices

router = APIRouter(prefix="/api/audio", tags=["audio"])


@router.get("/devices")
def get_devices() -> list[dict]:
    return list_input_devices()
