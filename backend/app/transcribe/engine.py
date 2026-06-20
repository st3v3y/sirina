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
    # where a partially-bundled mlx_whisper "exists" but fails to initialize. In the packaged
    # build mlx is excluded (see backend.spec), so this fails fast and we use faster-whisper;
    # in dev (mlx installed) it loads and the GPU path is used.
    try:
        import mlx_whisper  # noqa: F401
    except Exception:
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

    if choice == "faster-whisper":
        engine: TranscriptionEngine = _faster()
    elif choice == "mlx":
        if not _apple_silicon():
            log.warning("TRANSCRIPTION_ENGINE=mlx but not on Apple Silicon; using faster-whisper")
            engine = _faster()
        elif not _mlx_available():
            log.warning("TRANSCRIPTION_ENGINE=mlx but mlx_whisper is not importable; using faster-whisper")
            engine = _faster()
        else:
            engine = _mlx()
    else:  # auto
        engine = _mlx() if _mlx_available() else _faster()

    log.info("selected transcription engine: %s", engine.name)
    return engine
