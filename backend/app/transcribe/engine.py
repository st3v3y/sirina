"""Common transcription-engine interface and hardware-aware selection.

`WhisperKitEngine` (Apple Neural Engine via the speech helper, default on Apple Silicon)
and `FasterWhisperWorker` (CPU, fallback everywhere) satisfy `TranscriptionEngine`, so the
rest of the app is engine-agnostic. The job drives every engine window by window.
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

    async def transcribe_window(
        self,
        path: str,
        start_s: float,
        end_s: float | None,
        *,
        language: str | None = None,
    ) -> tuple[list[TLine], str | None]:
        """Transcribe `[start_s, end_s)` with word timestamps; times are absolute."""
        ...


def _apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def _whisperkit_unavailable_reason() -> str | None:
    """None when the WhisperKit helper can run here, else a user-facing reason."""
    if not _apple_silicon():
        return "WhisperKit needs an Apple Silicon Mac — using faster-whisper (CPU)."
    from .speech_helper import probe

    caps = probe()
    if not caps:
        return "The speech helper isn't available in this build (or needs macOS 14+) — using faster-whisper (CPU)."
    if not caps.get("whisperkit"):
        return "The speech helper can't run WhisperKit here — using faster-whisper (CPU)."
    return None


def select_engine() -> TranscriptionEngine:
    """Pick the transcription engine once, at startup (or on an explicit reload).

    `auto` (default) and `whisperkit` → WhisperKit on Apple Silicon when the speech helper
    runs (its model downloads on first load), else faster-whisper with the reason recorded
    for Settings. A stored `mlx` value (no longer offered) is treated as `auto`.
    """
    choice = (settings.transcription_engine or "auto").strip().lower()
    if choice == "mlx":
        log.info("TRANSCRIPTION_ENGINE=mlx is no longer supported; using auto")
        choice = "auto"

    note: str | None = None
    if choice == "faster-whisper":
        from .whisper import FasterWhisperWorker

        engine: TranscriptionEngine = FasterWhisperWorker()
    else:
        reason = _whisperkit_unavailable_reason()
        if reason is None:
            from .whisperkit import WhisperKitEngine

            engine = WhisperKitEngine()
        else:
            from .whisper import FasterWhisperWorker

            note = reason
            log.warning("WhisperKit unavailable (%s)", reason)
            engine = FasterWhisperWorker()

    # Record (or clear) why the active engine may differ from the chosen one, so the
    # Settings UI can explain a fallback instead of just showing faster-whisper.
    try:
        from ..runtime import runtime

        runtime.engine_note = note
    except Exception:
        pass

    log.info("selected transcription engine: %s", engine.name)
    return engine
