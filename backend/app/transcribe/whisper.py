from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from faster_whisper import WhisperModel

try:
    from faster_whisper import BatchedInferencePipeline
except Exception:  # pragma: no cover - older faster-whisper
    BatchedInferencePipeline = None  # type: ignore[assignment]

from ..config import settings

log = logging.getLogger(__name__)

from dataclasses import dataclass, field


# One word with timing: (start_seconds, end_seconds, text)
Word = tuple[float, float, str]


@dataclass
class TLine:
    """A transcribed line with optional word-level timestamps (for diarization)."""

    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


class FasterWhisperWorker:
    """Wraps faster-whisper with a single thread executor so inference doesn't block the event loop."""

    def __init__(self) -> None:
        self._model: WhisperModel | None = None
        self._batched = None
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
        if BatchedInferencePipeline is not None:
            try:
                self._batched = BatchedInferencePipeline(model=self._model)
            except Exception:
                log.warning("BatchedInferencePipeline unavailable; using sequential transcribe", exc_info=True)
                self._batched = None
        log.info("faster-whisper ready")

    async def transcribe_file(self, path: str) -> tuple[list[TLine], str | None]:
        """Transcribe a whole audio file with offline-quality settings.

        Returns (lines, language) where each line carries word-level timestamps.
        Runs in the worker's thread executor.
        """
        if self._model is None:
            raise RuntimeError("whisper model not loaded")
        loop = asyncio.get_running_loop()
        async with self._lock:
            language = settings.whisper_language or None
            initial_prompt = settings.whisper_initial_prompt or None
            return await loop.run_in_executor(
                self._executor, self._run_file, path, language, initial_prompt
            )

    def _run_file(
        self, path: str, language: str | None, initial_prompt: str | None
    ) -> tuple[list[TLine], str | None]:
        assert self._model is not None
        common = dict(
            language=language,
            beam_size=5,
            vad_filter=True,
            word_timestamps=True,
            initial_prompt=initial_prompt,
        )
        if self._batched is not None:
            # Batched mode is much faster on long files. It processes windows
            # independently, so condition_on_previous_text does not apply.
            segments, info = self._batched.transcribe(path, batch_size=8, **common)
        else:
            segments, info = self._model.transcribe(
                path, condition_on_previous_text=True, **common
            )
        lines: list[TLine] = []
        for seg in segments:
            text = (seg.text or "").strip()
            if not text:
                continue
            words: list[Word] = []
            for w in (getattr(seg, "words", None) or []):
                wt = (w.word or "").strip()
                if wt and w.start is not None and w.end is not None:
                    words.append((float(w.start), float(w.end), wt))
            lines.append(TLine(float(seg.start), float(seg.end), text, words))
        detected = getattr(info, "language", None)
        return lines, (language or detected)

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
