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


def _shift(ln: TLine, offset: float) -> TLine:
    if not offset:
        return ln
    return TLine(
        ln.start + offset,
        ln.end + offset,
        ln.text,
        [(w0 + offset, w1 + offset, t) for (w0, w1, t) in ln.words],
    )


def _sysctl_int(name: str) -> int | None:
    """Read an integer sysctl (macOS) via libc; None when unavailable."""
    import ctypes
    import ctypes.util

    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c"))
        value = ctypes.c_int(0)
        size = ctypes.c_size_t(ctypes.sizeof(value))
        if libc.sysctlbyname(name.encode(), ctypes.byref(value), ctypes.byref(size), None, 0) != 0:
            return None
        return value.value or None
    except Exception:
        return None


def default_cpu_threads(configured: int = 0) -> int:
    """Thread count for the CPU engine. A configured value wins; otherwise one thread per
    performance core on Apple Silicon (the efficiency cores slow the parallel decode down:
    6 threads ran 1.6x faster than 8 on an M1 Pro with identical text), else all cores."""
    if configured > 0:
        return configured
    perf = _sysctl_int("hw.perflevel0.physicalcpu")
    return perf or (os.cpu_count() or 1)


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
            cpu_threads = default_cpu_threads(settings.whisper_cpu_threads)
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

    async def transcribe_window(
        self,
        path: str,
        start_s: float,
        end_s: float | None,
        *,
        language: str | None = None,
    ) -> tuple[list[TLine], str | None]:
        """Transcribe `[start_s, end_s)` of a WAV with the offline-quality settings. Times
        are absolute (recording time). `language` (e.g. detected on an earlier window)
        overrides the configured one. The batched pipeline already decodes ~30 s VAD chunks
        independently, so a window cut at a silence gives the same text as the whole file."""
        if self._model is None:
            raise RuntimeError("whisper model not loaded")
        from ..audio.wav import load_wav_16k

        loop = asyncio.get_running_loop()
        async with self._lock:
            audio = await loop.run_in_executor(self._executor, load_wav_16k, path, start_s, end_s)
            if audio.size == 0:
                return [], language
            lang = language or settings.whisper_language or None
            initial_prompt = settings.whisper_initial_prompt or None
            lines, detected = await loop.run_in_executor(
                self._executor, self._run_file, audio, lang, initial_prompt, True, None
            )
        return [_shift(ln, start_s) for ln in lines], detected

    def _run_file(
        self,
        path,  # str path or a 16 kHz float32 array
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
