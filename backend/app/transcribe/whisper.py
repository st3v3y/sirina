from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from ..config import settings

log = logging.getLogger(__name__)

from dataclasses import dataclass, field


from collections.abc import Callable

# One word with timing: (start_seconds, end_seconds, text)
Word = tuple[float, float, str]

# No real word takes longer than this. With VAD, a word straddling two speech chunks is
# restored with its end in the later chunk — minutes after its start. Its start is the
# reliable side; the end is clamped so nothing downstream (diarization, segmentation,
# echo detection) sees a word claiming minutes of silence.
MAX_WORD_S = 2.0


def make_word(start: float, end: float, text: str) -> Word:
    return (start, min(end, start + MAX_WORD_S), text)


def line_from(start: float, end: float, text: str, words: list[Word]) -> "TLine":
    """A TLine whose bounds come from its (sanitized) words when it has them — segment
    times are coarser and can span silence."""
    if words:
        return TLine(words[0][0], words[-1][1], text, words)
    return TLine(start, end, text, words)

# Progress callback: (done_seconds, total_seconds). Called as transcription advances.
ProgressCb = Callable[[float, float], None]


@dataclass
class TLine:
    """A transcribed line with optional word-level timestamps (for diarization)."""

    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


class FasterWhisperWorker:
    """Wraps faster-whisper with a single thread executor so inference doesn't block the event loop."""

    name = "faster-whisper"
    streams_progress = True  # reports a real per-segment fraction via progress_cb

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
        # Lazy import: keep faster-whisper/ctranslate2 off the app's startup path so the
        # backend answers /api/status quickly; the heavy import happens here, in the
        # background load task.
        from faster_whisper import WhisperModel

        try:
            from faster_whisper import BatchedInferencePipeline
        except Exception:  # older faster-whisper
            BatchedInferencePipeline = None
        loop = asyncio.get_running_loop()

        def _load() -> "WhisperModel":
            cpu_threads = settings.whisper_cpu_threads or (os.cpu_count() or 0)
            log.info(
                "loading faster-whisper model=%s compute_type=%s cpu_threads=%s",
                settings.whisper_model,
                settings.whisper_compute_type,
                cpu_threads,
            )
            return WhisperModel(
                settings.whisper_model,
                device="cpu",
                compute_type=settings.whisper_compute_type,
                cpu_threads=cpu_threads,
            )

        self._model = await loop.run_in_executor(self._executor, _load)
        if BatchedInferencePipeline is not None:
            try:
                self._batched = BatchedInferencePipeline(model=self._model)
            except Exception:
                log.warning("BatchedInferencePipeline unavailable; using sequential transcribe", exc_info=True)
                self._batched = None
        log.info("faster-whisper ready")

    async def transcribe_file(
        self,
        path: str,
        *,
        word_timestamps: bool = True,
        progress_cb: ProgressCb | None = None,
    ) -> tuple[list[TLine], str | None]:
        """Transcribe a whole audio file with offline-quality settings.

        `word_timestamps` gives accurate line timing (needed to interleave tracks and for
        diarization); skipping it is faster but segment times can span long silences.
        `progress_cb(done_seconds, total_seconds)` is called as segments arrive.
        Returns (lines, language). Runs in the worker's thread executor.
        """
        if self._model is None:
            raise RuntimeError("whisper model not loaded")
        loop = asyncio.get_running_loop()
        async with self._lock:
            language = settings.whisper_language or None
            initial_prompt = settings.whisper_initial_prompt or None
            return await loop.run_in_executor(
                self._executor, self._run_file, path, language, initial_prompt, word_timestamps, progress_cb
            )

    def _run_file(
        self,
        path: str,
        language: str | None,
        initial_prompt: str | None,
        word_timestamps: bool,
        progress_cb: ProgressCb | None = None,
    ) -> tuple[list[TLine], str | None]:
        assert self._model is not None
        common = dict(
            language=language,
            beam_size=settings.whisper_beam_size,
            vad_filter=True,
            word_timestamps=word_timestamps,
            initial_prompt=initial_prompt,
            # Vocabulary hints (initial_prompt) can make the decoder latch onto a hint word
            # and emit it dozens of times ("FOKS FOKS FOKS…"). These bound that loop without
            # hurting normal speech: no n-gram of this length may repeat, and repeated tokens
            # are penalised. compression_ratio_threshold (default on) is the backstop.
            no_repeat_ngram_size=3,
            repetition_penalty=1.15,
        )
        if self._batched is not None:
            # Batched mode is much faster on long files. It processes windows
            # independently, so condition_on_previous_text does not apply.
            segments, info = self._batched.transcribe(path, batch_size=8, **common)
        else:
            segments, info = self._model.transcribe(
                path, condition_on_previous_text=True, **common
            )
        total = float(getattr(info, "duration", 0.0) or 0.0)
        lines: list[TLine] = []
        for seg in segments:
            if progress_cb and total > 0:
                progress_cb(float(seg.end), total)
            text = (seg.text or "").strip()
            if not text:
                continue
            words: list[Word] = []
            for w in (getattr(seg, "words", None) or []):
                wt = (w.word or "").strip()
                if wt and w.start is not None and w.end is not None:
                    words.append(make_word(float(w.start), float(w.end), wt))
            lines.append(line_from(float(seg.start), float(seg.end), text, words))
        if progress_cb and total > 0:
            progress_cb(total, total)  # ensure we end at 100%
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
