from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from faster_whisper import WhisperModel

from ..config import settings

log = logging.getLogger(__name__)


class FasterWhisperWorker:
    """Wraps faster-whisper with a single thread executor so inference doesn't block the event loop."""

    def __init__(self) -> None:
        self._model: WhisperModel | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper")
        self._lock = asyncio.Lock()

    def is_loaded(self) -> bool:
        return self._model is not None

    async def load(self) -> None:
        if self._model is not None:
            return
        loop = asyncio.get_running_loop()

        def _load() -> WhisperModel:
            log.info(
                "loading faster-whisper model=%s compute_type=%s",
                settings.whisper_model,
                settings.whisper_compute_type,
            )
            return WhisperModel(
                settings.whisper_model,
                device="cpu",
                compute_type=settings.whisper_compute_type,
            )

        self._model = await loop.run_in_executor(self._executor, _load)
        log.info("faster-whisper ready")

    async def transcribe(self, audio: np.ndarray) -> str:
        """audio: float32 mono 16 kHz numpy array."""
        if self._model is None:
            raise RuntimeError("whisper model not loaded")
        if audio.size == 0:
            return ""

        loop = asyncio.get_running_loop()
        async with self._lock:
            language = settings.whisper_language or None
            initial_prompt = settings.whisper_initial_prompt or None
            text = await loop.run_in_executor(
                self._executor,
                self._run,
                audio,
                language,
                initial_prompt,
            )
        return text

    def _run(self, audio: np.ndarray, language: str | None, initial_prompt: str | None) -> str:
        assert self._model is not None
        segments, _info = self._model.transcribe(
            audio,
            language=language,
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
            word_timestamps=False,
            initial_prompt=initial_prompt,
        )
        parts: list[str] = []
        for seg in segments:
            t = seg.text.strip()
            if t:
                parts.append(t)
        return " ".join(parts).strip()
