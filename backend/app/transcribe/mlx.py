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
        from mlx_whisper.audio import SAMPLE_RATE, load_audio

        chunk_s = settings.transcribe_chunk_seconds
        common = dict(
            path_or_hf_repo=self._repo,
            language=language,
            initial_prompt=initial_prompt,
            word_timestamps=word_timestamps,
        )

        # Single pass when chunking is disabled.
        if chunk_s <= 0:
            result = mlx_whisper.transcribe(path, **common)
            if progress_cb:
                progress_cb(1.0, 1.0)
            return self._lines_from_result(result, 0.0), (result.get("language") or language)

        # Chunked: load the waveform once (16 kHz mono float32), slice into windows,
        # transcribe each, offset timestamps, and report a real fraction per chunk.
        audio = load_audio(path)
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
