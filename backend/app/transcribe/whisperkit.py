"""WhisperKit engine: large-v3-turbo on the Apple Neural Engine via the speech helper.

Same interface as `FasterWhisperWorker`, driven window by window by the job. Uses ~0.4 GB
of RAM and little CPU (benchmark 2026-10-06: 59 s per 10 min of dense speech on an M1 Pro,
vs 193 s for faster-whisper large-v3). The first load prepares the model for the Neural
Engine (a few minutes, once; macOS caches it afterwards).
"""
from __future__ import annotations

import logging

from .. import speech_models
from ..config import settings
from .speech_helper import SpeechHelper, shared_helper
from .whisper import ProgressCb, TLine, Word

log = logging.getLogger(__name__)


def lines_from_segments(segments: list[dict]) -> list[TLine]:
    """Helper JSON segments → TLines (times already absolute)."""
    lines: list[TLine] = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        words: list[Word] = [
            (float(w[0]), float(w[1]), str(w[2]).strip())
            for w in seg.get("words") or []
            if len(w) == 3 and str(w[2]).strip()
        ]
        lines.append(TLine(float(seg["start"]), float(seg["end"]), text, words))
    return lines


class WhisperKitEngine:
    name = "whisperkit"
    streams_progress = True  # the job reports a fraction per window

    def __init__(self, helper: SpeechHelper | None = None, spec: speech_models.ModelSpec | None = None) -> None:
        self._helper = helper or shared_helper()
        self._spec = spec or speech_models.WHISPERKIT_TURBO
        self._loaded = False
        self.preparing = False  # downloading or preparing the model (first run)

    def is_loaded(self) -> bool:
        return self._loaded

    async def load(self) -> None:
        if self._loaded:
            return
        self.preparing = True
        try:
            folder = speech_models.model_dir(self._spec)
            if folder is None:
                log.info("WhisperKit model %s not installed; downloading", self._spec.id)
                await speech_models.install(self._spec.id)
                folder = speech_models.model_dir(self._spec)
                if folder is None:
                    err = speech_models._installs.get(self._spec.id, {}).get("error") or "download failed"
                    raise RuntimeError(f"WhisperKit model unavailable: {err}")
            await self._helper.request("load_whisper", model_dir=str(folder))
            self._loaded = True
            log.info("WhisperKit ready (%s)", self._spec.id)
        finally:
            self.preparing = False

    async def transcribe_window(
        self,
        path: str,
        start_s: float,
        end_s: float | None,
        *,
        language: str | None = None,
    ) -> tuple[list[TLine], str | None]:
        if not self._loaded:
            raise RuntimeError("whisperkit model not loaded")
        resp = await self._helper.request(
            "transcribe",
            path=path,
            start_s=start_s,
            end_s=end_s,
            language=language or settings.whisper_language or None,
            prompt=settings.whisper_initial_prompt or None,
        )
        return lines_from_segments(resp.get("segments") or []), resp.get("language") or language

    async def transcribe_file(
        self,
        path: str,
        *,
        word_timestamps: bool = True,
        progress_cb: ProgressCb | None = None,
    ) -> tuple[list[TLine], str | None]:
        """Whole-file call kept for interface compatibility (the job uses windows)."""
        lines, lang = await self.transcribe_window(path, 0.0, None)
        if progress_cb:
            progress_cb(1.0, 1.0)
        return lines, lang
