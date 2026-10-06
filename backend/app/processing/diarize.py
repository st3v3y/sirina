"""Optional local speaker diarization via pyannote.audio.

Gated by `DIARIZATION_ENABLED` + `HF_TOKEN`. Loads lazily and runs inference in a
thread executor. Any failure is the caller's cue to fall back to the baseline split.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ..config import settings

log = logging.getLogger(__name__)

# A diarization turn: (start_seconds, end_seconds, cluster_label)
Turn = tuple[float, float, str]


@dataclass
class DiarizationResult:
    turns: list[Turn]
    # cluster label -> speaker embedding (centroid). Empty when the pipeline didn't
    # expose embeddings — diarization still works, only voice matching is skipped.
    embeddings: dict[str, list[float]] = field(default_factory=dict)


_DIAR_SR = 16_000  # pyannote's native rate


def _load_waveform(path: str) -> dict:
    """Load a 16-bit PCM WAV as pyannote's in-memory input ({"waveform", "sample_rate"}).
    Bypasses pyannote's torchcodec-based file decoder (unavailable in packaged builds).

    Read in blocks and resampled to 16 kHz as we go: a multi-hour 48 kHz track held whole
    as int16 + float32 (and resampled again inside pyannote) peaks at several GB."""
    import wave
    from math import gcd

    import numpy as np
    import torch
    from scipy.signal import resample_poly

    parts: list[np.ndarray] = []
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        channels = wf.getnchannels()
        if wf.getsampwidth() != 2:
            raise RuntimeError(f"expected 16-bit PCM wav, got sample width {wf.getsampwidth()}")
        g = gcd(int(sr), _DIAR_SR)
        up, down = _DIAR_SR // g, int(sr) // g
        block = sr * 60  # one minute per block; boundary effects are inaudible to embeddings
        while True:
            raw = wf.readframes(block)
            if not raw:
                break
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            if channels > 1:
                arr = arr.reshape(-1, channels).mean(axis=1)
            if up != down:
                arr = resample_poly(arr, up, down).astype(np.float32)
            parts.append(arr)
    audio = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
    return {"waveform": torch.from_numpy(audio).unsqueeze(0), "sample_rate": _DIAR_SR}


def pyannote_bundled() -> bool:
    """Whether pyannote.audio exists in this build at all. The packaged app excludes
    it unless built with --diarization, and enabling the setting can't conjure it."""
    try:
        import importlib.util

        return importlib.util.find_spec("pyannote.audio") is not None
    except Exception:
        return False


class Diarizer:
    def __init__(self) -> None:
        self._pipeline = None
        self._loaded = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="diarize")
        self._lock = asyncio.Lock()
        self._bundled = pyannote_bundled()

    def is_available(self) -> bool:
        return bool(self._bundled and settings.diarization_enabled and settings.hf_token)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        from pyannote.audio import Pipeline  # imported lazily (heavy)

        model_id = settings.diarization_model
        log.info("loading pyannote diarization model %s", model_id)
        try:
            # pyannote.audio 4.x
            pipeline = Pipeline.from_pretrained(model_id, token=settings.hf_token)
        except TypeError:
            # pyannote.audio 3.x
            pipeline = Pipeline.from_pretrained(model_id, use_auth_token=settings.hf_token)
        if pipeline is None:
            raise RuntimeError(
                "pyannote pipeline failed to load — check HF_TOKEN and that you've accepted "
                "the model terms for pyannote/segmentation-3.0 and pyannote/speaker-diarization-3.1"
            )
        try:
            import torch

            if torch.backends.mps.is_available():
                pipeline.to(torch.device("mps"))
        except Exception:
            log.debug("MPS unavailable for pyannote; using CPU", exc_info=True)
        self._pipeline = pipeline
        self._loaded = True
        log.info("pyannote ready")

    async def diarize(self, path: str) -> DiarizationResult:
        """Return diarization turns (and per-cluster embeddings when the pipeline
        exposes them) for an audio file. Raises on failure."""
        loop = asyncio.get_running_loop()
        async with self._lock:
            return await loop.run_in_executor(self._executor, self._run, path)

    def _run(self, path: str) -> DiarizationResult:
        self._ensure_loaded()
        assert self._pipeline is not None
        # Feed pyannote an in-memory waveform instead of a file path: path decoding goes
        # through torchcodec, which vendors an incompatible libpython that breaks the
        # frozen app (so backend.spec excludes it — see the comment there). Our tracks
        # are plain PCM WAVs, trivially loaded with the stdlib.
        try:
            audio = _load_waveform(path)
        except Exception:
            log.debug("in-memory wav load failed for %s; passing the path", path, exc_info=True)
            audio = path
        # Ask for per-speaker embeddings (the clustering centroids) so recurring people
        # can be recognised across recordings. Older/other pipelines may not accept the
        # kwarg — diarization itself must never fail because of it.
        raw_embeddings = None
        try:
            result = self._pipeline(audio, return_embeddings=True)
        except TypeError:
            result = self._pipeline(audio)
        # pyannote 3.x with return_embeddings returns an (Annotation, ndarray) tuple;
        # 4.x returns a DiarizeOutput object.
        if isinstance(result, tuple) and len(result) == 2:
            result, raw_embeddings = result
        else:
            raw_embeddings = getattr(result, "speaker_embeddings", None)
            if raw_embeddings is None:
                raw_embeddings = getattr(result, "embeddings", None)
        # pyannote 4.x returns a DiarizeOutput (use the exclusive, non-overlapping
        # annotation for clean segment alignment); 3.x returns an Annotation directly.
        annotation = (
            getattr(result, "exclusive_speaker_diarization", None)
            or getattr(result, "speaker_diarization", None)
            or result
        )
        turns: list[Turn] = []
        for turn, _track, speaker in annotation.itertracks(yield_label=True):
            turns.append((float(turn.start), float(turn.end), str(speaker)))
        turns.sort(key=lambda t: t[0])
        # Embedding rows align with the FULL diarization's speaker order — the exclusive
        # variant may drop a fully-overlapped speaker and misalign the mapping.
        emb_annotation = getattr(result, "speaker_diarization", None) or annotation
        return DiarizationResult(turns, self._embeddings_by_label(emb_annotation, raw_embeddings))

    @staticmethod
    def _embeddings_by_label(annotation, raw) -> dict[str, list[float]]:
        """Map cluster labels to embedding rows. Pipelines return one row per speaker
        in `annotation.labels()` order; rows can contain NaN for speakers the model
        couldn't embed cleanly — those are skipped. Best-effort: any surprise in the
        shape just disables voice matching for this run."""
        if raw is None:
            return {}
        try:
            labels = list(annotation.labels())
            if len(labels) != len(raw):
                log.debug(
                    "embedding rows (%d) don't match speaker labels (%d); skipping",
                    len(raw), len(labels),
                )
                return {}
            out: dict[str, list[float]] = {}
            for label, row in zip(labels, raw):
                vec = [float(x) for x in row]
                if any(x != x for x in vec):  # NaN row → no clean embedding
                    continue
                out[str(label)] = vec
            return out
        except Exception:
            log.debug("could not extract speaker embeddings", exc_info=True)
            return {}


def assign_clusters(units: list[tuple[float, float, str]], turns: list[Turn]) -> list[str]:
    """For each (start, end, text) unit, return the diarization cluster with the greatest
    temporal overlap. Units with no overlap fall back to the nearest turn by midpoint.

    Both units (transcript order) and turns (sorted by diarize()) are time-ordered, so a
    two-pointer merge does this in O(units + turns) — the old per-unit full scan was
    O(units × turns), ~10⁸ comparisons on a multi-hour meeting. Out-of-order units are
    handled by rewinding the pointer, degrading gracefully instead of misassigning."""
    labels: list[str] = []
    n = len(turns)
    i = 0  # first turn whose end may still overlap the current unit
    prev_start: float | None = None
    for start, end, _text in units:
        if prev_start is not None and start < prev_start:
            i = 0  # units went backwards — rescan from the top to stay correct
        prev_start = start
        while i < n and turns[i][1] <= start:
            i += 1
        best_label: str | None = None
        best_overlap = 0.0
        j = i
        while j < n and turns[j][0] < end:
            t_start, t_end, cluster = turns[j]
            overlap = min(end, t_end) - max(start, t_start)
            if overlap > best_overlap:
                best_overlap = overlap
                best_label = cluster
            j += 1
        if best_label is None and turns:
            # The unit sits in a silence gap: the nearest turn by midpoint is (one of)
            # the pointer's neighbours — check a small window around it.
            mid = (start + end) / 2
            window = turns[max(0, i - 8) : min(n, i + 8)] or turns
            best_label = min(window, key=lambda t: abs(((t[0] + t[1]) / 2) - mid))[2]
        labels.append(best_label or "SPEAKER_00")
    return labels


def diarize_lines(lines, turns: list[Turn]):
    """Re-segment transcript lines by speaker using word-level timing.

    Each word is assigned to its max-overlap diarization cluster; consecutive words
    with the same cluster are regrouped into a new line. Falls back to whole-line
    units when a line lacks word timestamps. Returns a list of (cluster, TLine)."""
    from ..transcribe.whisper import TLine  # local import avoids a cycle
    from .segment import LONG_GAP_S

    # Flatten to (start, end, text) units, remembering which line each came from.
    units: list[tuple[float, float, str]] = []
    for ln in lines:
        if ln.words:
            units.extend(ln.words)
        else:
            units.append((ln.start, ln.end, ln.text))
    if not units:
        return []

    clusters = assign_clusters(units, turns)

    groups: list[tuple[str, "TLine"]] = []
    cur_cluster: str | None = None
    cur: list[tuple[float, float, str]] = []

    def flush() -> None:
        if cur and cur_cluster is not None:
            text = " ".join(w[2] for w in cur).strip()
            groups.append((cur_cluster, TLine(cur[0][0], cur[-1][1], text, list(cur))))

    for unit, cluster in zip(units, clusters):
        # Also break at a long silence: consecutive same-cluster words are often minutes
        # apart (the user talked on the mic meanwhile), and a line spanning that gap
        # inflates the cluster's duration and its overlap with the mic (echo detection).
        if cluster != cur_cluster or (cur and unit[0] - cur[-1][1] >= LONG_GAP_S):
            flush()
            cur_cluster = cluster
            cur = [unit]
        else:
            cur.append(unit)
    flush()
    return groups
