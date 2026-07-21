"""Apple-GPU transcription via mlx-whisper (Apple Silicon only).

Same interface as `FasterWhisperWorker`. mlx-whisper returns all segments from a
single blocking call, so there is no streaming progress — the transcribing stage
is reported without a fraction (indeterminate) on this path.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from ..config import settings
from .whisper import ProgressCb, TLine, Word

log = logging.getLogger(__name__)

# whisper_model size → mlx-community HF repo. Override via MLX_WHISPER_REPO.
_MLX_REPOS = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large": "mlx-community/whisper-large-v3-mlx",
    "large-v1": "mlx-community/whisper-large-v1-mlx",
    "large-v2": "mlx-community/whisper-large-v2-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}
_DEFAULT_REPO = _MLX_REPOS["medium"]


def _load_audio_16k(path: str):
    """Decode a recording to 16 kHz mono float32 in [-1, 1] WITHOUT the `ffmpeg` CLI.

    mlx-whisper's own `load_audio` runs `ffmpeg`, which isn't bundled/on PATH in the
    packaged app. Our recordings are 16-bit PCM WAV (written by the recorder), so we read
    them directly with the stdlib `wave` module and resample to whisper's 16 kHz with
    SciPy (already bundled). The array is then passed straight to `transcribe()`."""
    import wave

    import numpy as np

    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        sampwidth = w.getsampwidth()
        raw = w.readframes(w.getnframes())

    if sampwidth != 2:
        raise RuntimeError(f"unsupported {sampwidth * 8}-bit WAV (expected 16-bit): {path}")

    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:  # downmix to mono
        audio = audio.reshape(-1, ch).mean(axis=1)
    if sr != 16000 and audio.size:
        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(int(sr), 16000)
        audio = resample_poly(audio, 16000 // g, int(sr) // g)
    return np.ascontiguousarray(audio, dtype=np.float32)


def _repo_for_model(model: str) -> str:
    if settings.mlx_whisper_repo:
        return settings.mlx_whisper_repo
    repo = _MLX_REPOS.get(model.strip().lower())
    if repo is None:
        log.warning("no MLX repo mapping for model %r; defaulting to %s", model, _DEFAULT_REPO)
        return _DEFAULT_REPO
    return repo


class MlxWhisperWorker:
    """Wraps mlx-whisper with a single thread executor."""

    name = "mlx"

    @property
    def streams_progress(self) -> bool:
        # With chunking enabled, each window reports a real fraction; otherwise the
        # single blocking call yields no progress (the job falls back to an estimate).
        return settings.transcribe_chunk_seconds > 0

    def __init__(self) -> None:
        self._loaded = False
        self._repo = _repo_for_model(settings.whisper_model)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx-whisper")
        self._lock = asyncio.Lock()

    def is_loaded(self) -> bool:
        return self._loaded

    async def load(self) -> None:
        if self._loaded:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._warm)
        self._loaded = True

    def _warm(self) -> None:
        """Download (first run) + load the model into the resident ModelHolder cache,
        so the ~GB download happens here at startup rather than silently inside the
        first transcription. Subsequent transcribes reuse the cached model."""
        import mlx.core as mx
        from mlx_whisper.transcribe import ModelHolder

        log.info("loading MLX model %s (first run downloads it, ~GB)…", self._repo)
        ModelHolder.get_model(self._repo, mx.float16)  # transcribe() defaults to fp16
        log.info("mlx-whisper ready (repo=%s)", self._repo)

    async def transcribe_file(
        self,
        path: str,
        *,
        word_timestamps: bool = True,
        progress_cb: ProgressCb | None = None,
    ) -> tuple[list[TLine], str | None]:
        loop = asyncio.get_running_loop()
        async with self._lock:
            language = settings.whisper_language or None
            initial_prompt = settings.whisper_initial_prompt or None
            return await loop.run_in_executor(
                self._executor, self._run_file, path, language, initial_prompt, word_timestamps, progress_cb
            )

    @staticmethod
    def _lines_from_result(result: dict, offset: float) -> list[TLine]:
        """Convert an mlx-whisper result to TLines, shifting times by `offset` seconds."""
        lines: list[TLine] = []
        for seg in result.get("segments", []) or []:
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            words: list[Word] = []
            for w in seg.get("words") or []:
                wt = (w.get("word") or "").strip()
                ws, we = w.get("start"), w.get("end")
                if wt and ws is not None and we is not None:
                    words.append((float(ws) + offset, float(we) + offset, wt))
            lines.append(
                TLine(float(seg.get("start", 0.0)) + offset, float(seg.get("end", 0.0)) + offset, text, words)
            )
        return lines

    def _run_file(
        self,
        path: str,
        language: str | None,
        initial_prompt: str | None,
        word_timestamps: bool,
        progress_cb: ProgressCb | None = None,
    ) -> tuple[list[TLine], str | None]:
        import mlx_whisper
        from mlx_whisper.audio import SAMPLE_RATE

        chunk_s = settings.transcribe_chunk_seconds
        common = dict(
            path_or_hf_repo=self._repo,
            language=language,
            initial_prompt=initial_prompt,
            word_timestamps=word_timestamps,
            # A vocabulary hint can send mlx-whisper into a repetition loop, echoing one hint
            # word many times. Not conditioning on previously decoded text stops the loop from
            # compounding window-to-window; compression_ratio_threshold (default) is the
            # backstop that retriggers decoding when a window comes out degenerate.
            condition_on_previous_text=False,
        )

        # Decode ourselves (NOT mlx-whisper's load_audio, which shells out to the `ffmpeg`
        # CLI — absent from the packaged app's PATH → "No such file or directory: 'ffmpeg'").
        # We always hand transcribe() a 16 kHz float32 array, so it never touches ffmpeg.
        audio = _load_audio_16k(path)

        # Single pass when chunking is disabled.
        if chunk_s <= 0:
            result = mlx_whisper.transcribe(audio, **common)
            if progress_cb:
                progress_cb(1.0, 1.0)
            return self._lines_from_result(result, 0.0), (result.get("language") or language)

        # Chunked: slice the waveform into windows, transcribe each, offset timestamps,
        # and report a real fraction per chunk.
        total_samples = len(audio)
        total_s = total_samples / SAMPLE_RATE
        if total_s <= chunk_s:
            result = mlx_whisper.transcribe(audio, **common)
            if progress_cb:
                progress_cb(total_s, total_s)
            return self._lines_from_result(result, 0.0), (result.get("language") or language)

        step = int(chunk_s * SAMPLE_RATE)
        lines: list[TLine] = []
        detected = language
        for start in range(0, total_samples, step):
            window = audio[start : start + step]
            offset = start / SAMPLE_RATE
            # Reuse the detected language across chunks for consistency + speed.
            result = mlx_whisper.transcribe(window, **{**common, "language": detected})
            detected = detected or result.get("language")
            lines.extend(self._lines_from_result(result, offset))
            if progress_cb:
                progress_cb(min((start + step) / SAMPLE_RATE, total_s), total_s)
        return lines, detected
