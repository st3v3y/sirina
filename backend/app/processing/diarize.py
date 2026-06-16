"""Optional local speaker diarization via pyannote.audio.

Gated by `DIARIZATION_ENABLED` + `HF_TOKEN`. Loads lazily and runs inference in a
thread executor. Any failure is the caller's cue to fall back to the baseline split.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from ..config import settings

log = logging.getLogger(__name__)

# A diarization turn: (start_seconds, end_seconds, cluster_label)
Turn = tuple[float, float, str]


class Diarizer:
    def __init__(self) -> None:
        self._pipeline = None
        self._loaded = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="diarize")
        self._lock = asyncio.Lock()

    def is_available(self) -> bool:
        return bool(settings.diarization_enabled and settings.hf_token)

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

    async def diarize(self, path: str) -> list[Turn]:
        """Return diarization turns for an audio file. Raises on failure."""
        loop = asyncio.get_running_loop()
        async with self._lock:
            return await loop.run_in_executor(self._executor, self._run, path)

    def _run(self, path: str) -> list[Turn]:
        self._ensure_loaded()
        assert self._pipeline is not None
        result = self._pipeline(path)
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
        return turns


def assign_clusters(units: list[tuple[float, float, str]], turns: list[Turn]) -> list[str]:
    """For each (start, end, text) unit, return the diarization cluster with the greatest
    temporal overlap. Units with no overlap fall back to the nearest turn by midpoint."""
    labels: list[str] = []
    for start, end, _text in units:
        best_label: str | None = None
        best_overlap = 0.0
        for t_start, t_end, cluster in turns:
            overlap = min(end, t_end) - max(start, t_start)
            if overlap > best_overlap:
                best_overlap = overlap
                best_label = cluster
        if best_label is None and turns:
            mid = (start + end) / 2
            best_label = min(turns, key=lambda t: abs(((t[0] + t[1]) / 2) - mid))[2]
        labels.append(best_label or "SPEAKER_00")
    return labels


def diarize_lines(lines, turns: list[Turn]):
    """Re-segment transcript lines by speaker using word-level timing.

    Each word is assigned to its max-overlap diarization cluster; consecutive words
    with the same cluster are regrouped into a new line. Falls back to whole-line
    units when a line lacks word timestamps. Returns a list of (cluster, TLine)."""
    from ..transcribe.whisper import TLine  # local import avoids a cycle

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
        if cluster != cur_cluster:
            flush()
            cur_cluster = cluster
            cur = [unit]
        else:
            cur.append(unit)
    flush()
    return groups
