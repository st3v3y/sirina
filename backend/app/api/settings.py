"""Read/update the user-editable settings, plus the transcription-engine reload action.

Fields and their metadata come from the registry in `settings_store`; the page renders
entirely from this, so adding a field is a registry edit, not bespoke API/UI work.
"""
from __future__ import annotations

import asyncio
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
    # Cheap presence check (no heavy import). The default packaged app excludes pyannote;
    # a --diarization build includes it (see scripts/build-macos-app.sh).
    from ..processing.diarize import pyannote_bundled

    return pyannote_bundled()


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
        rec_id = proc.current_id()
        where = f"Recording #{rec_id} is being processed" if rec_id else "A recording is being processed"
        return {
            "ok": False,
            "busy": True,
            "processing_id": rec_id,
            "detail": f"{where}. Wait for it to finish (open it to Stop processing), or restart the app.",
        }
    async with _reload_lock:
        from ..transcribe.engine import select_engine

        new = select_engine()
        try:
            await new.load()
        except Exception as e:  # also the retry path for a failed/offline first-run load
            runtime.whisper_error = f"{type(e).__name__}: {e}"
            log.exception("transcription engine reload failed")
            return {"ok": False, "detail": runtime.whisper_error}
        runtime.whisper = new
        runtime.whisper_error = None
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
            # The data dir is named after the bundle id (com.sirina.app), so its ".app"
            # suffix makes macOS treat it as an application bundle: a bare `open <dir>` — and
            # even `open -a Finder <dir>` once the real app is registered with LaunchServices —
            # tries to LAUNCH it ("can't open the application … it may be damaged or
            # incomplete"). `-R` reveals the folder (selected in its parent) instead of opening
            # it, sidestepping the bundle interpretation. Check the result so failures surface.
            proc = subprocess.run(
                ["/usr/bin/open", "-R", str(path)],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode != 0:
                raise RuntimeError((proc.stderr or proc.stdout or f"exit {proc.returncode}").strip())
        elif os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        log.warning("reveal data dir failed: %s", e)
        raise HTTPException(500, f"could not open folder: {e}")
    return {"ok": True}
