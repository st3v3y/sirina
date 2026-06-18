"""Read/update the user-editable settings, plus the transcription-engine reload action.

Fields and their metadata come from the registry in `settings_store`; the page renders
entirely from this, so adding a field is a registry edit, not bespoke API/UI work.
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import subprocess
import sys
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..runtime import runtime
from ..settings_store import FIELDS, apply, secret_get

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Serialize reloads so two clients can't swap the engine concurrently.
_reload_lock = asyncio.Lock()


class SettingField(BaseModel):
    key: str
    label: str
    section: str
    type: str
    options: list[str] | None = None
    options_source: str | None = None
    secret: bool = False
    restart: str = "none"
    help: str | None = None
    value: Any | None = None  # None for secrets (never returned in plaintext)
    is_set: bool | None = None  # secrets only: whether a value is configured


class SettingsResponse(BaseModel):
    fields: list[SettingField]
    data_dir: str
    diarization_supported: bool  # whether pyannote is importable in this build
    reload_required: bool = False


class SettingsPatch(BaseModel):
    updates: dict[str, Any]


def _diarization_supported() -> bool:
    # Cheap presence check (no heavy import). In the packaged app pyannote isn't bundled
    # yet, so the diarization toggle is exposed but inert until that lands.
    try:
        return importlib.util.find_spec("pyannote.audio") is not None
    except Exception:
        return False


def _render(reload_required: bool = False) -> SettingsResponse:
    fields: list[SettingField] = []
    for f in FIELDS:
        sf = SettingField(
            key=f.key, label=f.label, section=f.section, type=f.type,
            options=f.options, options_source=f.options_source, secret=f.secret,
            restart=f.restart, help=f.help,
        )
        if f.secret:
            sf.is_set = bool(secret_get(f.key))
        else:
            sf.value = getattr(settings, f.key)
        fields.append(sf)
    return SettingsResponse(
        fields=fields,
        data_dir=str(settings.data_dir),
        diarization_supported=_diarization_supported(),
        reload_required=reload_required,
    )


@router.get("", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    return _render()


@router.patch("", response_model=SettingsResponse)
async def update_settings(payload: SettingsPatch) -> SettingsResponse:
    try:
        result = apply(payload.updates)
    except ValueError as e:
        raise HTTPException(400, str(e))
    # Hot LLM changes apply immediately by rebuilding the client.
    if result.llm_changed:
        await runtime.rebuild_llm()
    return _render(reload_required=result.reload_required)


@router.post("/reload-engine")
async def reload_engine() -> dict[str, Any]:
    """Re-select and reload the transcription engine with the current settings. Refused
    while a recording is being processed (a mid-job model swap would corrupt it)."""
    proc = runtime.processor
    if proc is not None and proc.is_busy():
        return {
            "ok": False,
            "busy": True,
            "detail": "A recording is being processed. Wait for it to finish, or restart the app.",
        }
    async with _reload_lock:
        from ..transcribe.engine import select_engine

        new = select_engine()
        await new.load()
        runtime.whisper = new
        if runtime.processor is not None:
            runtime.processor.set_engine(new)
        if runtime.pipeline is not None:
            runtime.pipeline.whisper = new
    log.info("transcription engine reloaded: %s", getattr(new, "name", "unknown"))
    return {"ok": True, "engine": getattr(new, "name", "unknown")}


@router.post("/reveal-data-dir")
def reveal_data_dir() -> dict[str, bool]:
    """Open the app data folder in the OS file manager."""
    path = settings.data_dir
    path.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        raise HTTPException(500, f"could not open folder: {e}")
    return {"ok": True}
