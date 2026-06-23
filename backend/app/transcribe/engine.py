"""Common transcription-engine interface and hardware-aware selection.

Both `FasterWhisperWorker` (CPU, all platforms) and `MlxWhisperWorker` (Apple GPU)
satisfy `TranscriptionEngine`, so the rest of the app is engine-agnostic.
"""
from __future__ import annotations

import logging
import platform
from typing import Protocol, runtime_checkable

from ..config import settings
from .whisper import ProgressCb, TLine

log = logging.getLogger(__name__)


@runtime_checkable
class TranscriptionEngine(Protocol):
    name: str
    streams_progress: bool  # True if transcribe_file reports a real fraction via progress_cb

    def is_loaded(self) -> bool: ...

    async def load(self) -> None: ...

    async def transcribe_file(
        self,
        path: str,
        *,
        word_timestamps: bool = True,
        progress_cb: ProgressCb | None = None,
    ) -> tuple[list[TLine], str | None]: ...


def _apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def _mlx_available() -> bool:
    if not _apple_silicon():
        return False
    # Actually import to confirm it LOADS — find_spec is too optimistic in a frozen app,
    # where a partially-bundled mlx_whisper "exists" but fails to initialize. The import
    # pulls native libs (mlx's Metal kernels, llvmlite via numba) that can fail to load in a
    # codesigned .app even though they're present, so log the real reason — otherwise the
    # silent fallback to faster-whisper is impossible to diagnose from the field log.
    try:
        import mlx_whisper  # noqa: F401
    except Exception as e:
        log.warning("mlx_whisper import failed (%s: %s); using faster-whisper", type(e).__name__, e)
        log.debug("mlx_whisper import traceback", exc_info=True)
        return False
    return True


def select_engine() -> TranscriptionEngine:
    """Pick the transcription engine once, at startup.

    `auto` (default) → MLX on Apple Silicon when importable, else faster-whisper.
    An explicit `TRANSCRIPTION_ENGINE` overrides detection.
    """
    choice = (settings.transcription_engine or "auto").strip().lower()

    def _faster() -> TranscriptionEngine:
        from .whisper import FasterWhisperWorker

        return FasterWhisperWorker()

    def _mlx() -> TranscriptionEngine:
        from .mlx import MlxWhisperWorker

        return MlxWhisperWorker()

    note: str | None = None
    if choice == "faster-whisper":
        engine: TranscriptionEngine = _faster()
    elif choice == "mlx":
        if not _apple_silicon():
            note = "MLX needs Apple Silicon — using faster-whisper (CPU)."
            log.warning("TRANSCRIPTION_ENGINE=mlx but not on Apple Silicon; using faster-whisper")
            engine = _faster()
        elif not _mlx_available():
            note = "MLX isn't bundled in this build — using faster-whisper (CPU)."
            log.warning("TRANSCRIPTION_ENGINE=mlx but mlx_whisper is not importable; using faster-whisper")
            engine = _faster()
        else:
            engine = _mlx()
    else:  # auto
        engine = _mlx() if _mlx_available() else _faster()

    # Record (or clear) why the active engine may differ from the chosen one, so the
    # Settings UI can explain a silent fallback instead of just showing faster-whisper.
    try:
        from ..runtime import runtime

        runtime.engine_note = note
    except Exception:
        pass

    log.info("selected transcription engine: %s", engine.name)
    return engine
