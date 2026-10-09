"""Optional local speaker splitting (diarization) with SpeakerKit.

Runs on-device through the speech helper (`native/speech-engine`), sharing its request
lock with transcription. Gated by the `diarization_enabled` setting; no account or token
is needed (the ~60 MB model downloads on first use). Benchmark 2026-10-06 on a 2h14
track: 52 s and 3.6 GB vs pyannote's 575 s and 7.2 GB, agreeing on ~94% of speech time.
Any failure is the caller's cue to fall back to the baseline split.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..config import settings

log = logging.getLogger(__name__)

# A diarization turn: (start_seconds, end_seconds, cluster_label)
Turn = tuple[float, float, str]

# Voice fingerprints are only comparable with fingerprints from the same model.
VOICEPRINT_MODEL = "speakerkit-pyannote-v3"


@dataclass
class DiarizationResult:
    turns: list[Turn]
    # cluster label -> speaker embedding (centroid). Empty when the model didn't expose
    # embeddings — diarization still works, only voice matching is skipped.
    embeddings: dict[str, list[float]] = field(default_factory=dict)


def diarization_supported() -> bool:
    """Whether this build/Mac can split speakers at all (speech helper with SpeakerKit)."""
    from ..transcribe.speech_helper import probe

    return bool(probe().get("speakerkit"))


def diarization_reason() -> str | None:
    """Why speaker splitting can't run here (None when it can)."""
    if diarization_supported():
        return None
    from ..osinfo import platform_label, platform_name

    if platform_name() == "macos":
        return "Speaker separation needs the on-device speech helper (macOS 14+ on Apple Silicon)."
    return f"Speaker separation isn't available on {platform_label()} yet."


class Diarizer:
    """Speaker splitting via SpeakerKit in the speech helper."""

    def __init__(self, helper=None) -> None:
        from ..transcribe.speech_helper import shared_helper

        self._helper = helper or shared_helper()
        self._loaded = False

    def is_available(self) -> bool:
        return bool(settings.diarization_enabled and diarization_supported())

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        from .. import speech_models

        folder = speech_models.model_dir(speech_models.SPEAKERKIT)
        if folder is None:
            log.info("speaker model not installed; downloading")
            await speech_models.install(speech_models.SPEAKERKIT.id)
            folder = speech_models.model_dir(speech_models.SPEAKERKIT)
            if folder is None:
                err = speech_models._installs.get(speech_models.SPEAKERKIT.id, {}).get("error") or "download failed"
                raise RuntimeError(f"speaker model unavailable: {err}")
        await self._helper.request("load_diarizer", model_dir=str(folder))
        self._loaded = True

    async def diarize(self, path: str, end_s: float | None = None) -> DiarizationResult:
        """Turns and per-speaker embeddings for a WAV (up to `end_s`). Raises on failure."""
        await self._ensure_loaded()
        resp = await self._helper.request("diarize", path=path, end_s=end_s)
        turns: list[Turn] = sorted(
            (float(t["start"]), float(t["end"]), str(t["speaker"])) for t in resp.get("turns") or []
        )
        embeddings = {
            str(k): [float(x) for x in v]
            for k, v in (resp.get("embeddings") or {}).items()
            if v and not any(x != x for x in v)  # skip NaN rows
        }
        return DiarizationResult(turns, embeddings)


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
