"""Background transcription processor: one job at a time, restart-safe.

Pulls recording ids off a queue, transcribes the recording's audio with the
offline-quality whisper path, writes Segment rows, and flips the recording to
`ready` (or `failed`).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from sqlmodel import Session, delete, select

from ..db import engine
from ..models import Recording, Segment, Speaker
from ..transcribe.whisper import FasterWhisperWorker
from .diarize import Diarizer, diarize_lines

if TYPE_CHECKING:
    from ..pipeline import Pipeline

log = logging.getLogger(__name__)

# Stable colour tokens assigned to speakers in creation order; the frontend maps
# each token to a palette.
_SPEAKER_COLORS = ["sky", "emerald", "violet", "amber", "rose", "teal"]


def _color(i: int) -> str:
    return _SPEAKER_COLORS[i % len(_SPEAKER_COLORS)]


class TranscriptionProcessor:
    def __init__(
        self,
        whisper: FasterWhisperWorker,
        pipeline: "Pipeline | None" = None,
        diarizer: Diarizer | None = None,
    ) -> None:
        self._whisper = whisper
        self._pipeline = pipeline
        self._diarizer = diarizer
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="transcription-processor")

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def enqueue(self, recording_id: int) -> None:
        await self._queue.put(recording_id)

    async def requeue_pending(self) -> None:
        """Re-enqueue any recordings left in `processing` (e.g. after a restart)."""
        with Session(engine) as s:
            ids = s.exec(select(Recording.id).where(Recording.status == "processing")).all()  # type: ignore[arg-type]
        for rid in ids:
            if rid is not None:
                await self._queue.put(rid)
        if ids:
            log.info("re-enqueued %d pending recording(s) for transcription", len(ids))

    async def _run(self) -> None:
        while True:
            recording_id = await self._queue.get()
            try:
                await self._process(recording_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("transcription job failed for recording %d", recording_id)
                self._mark_failed(recording_id, "transcription job error")
            finally:
                self._queue.task_done()

    async def _process(self, recording_id: int) -> None:
        with Session(engine) as s:
            rec = s.get(Recording, recording_id)
            if rec is None:
                return
            audio_path = rec.audio_path
            mic_path = rec.mic_path
            system_path = rec.system_path
            label = rec.label

        if not audio_path or not Path(audio_path).exists():
            self._mark_failed(recording_id, "audio file missing")
            return

        await self._whisper.load()
        two_track = bool(mic_path and system_path and Path(mic_path).exists() and Path(system_path).exists())
        use_diar = self._diarizer is not None and self._diarizer.is_available()

        # (speaker_label, color, list of (start, end, text)) per resulting speaker
        tracks: list[tuple[str, str, list]] = []
        if two_track:
            log.info("transcribing recording %d (two-track: mic + system)", recording_id)
            mic_lines, language = await self._whisper.transcribe_file(mic_path)  # type: ignore[arg-type]
            sys_lines, _ = await self._whisper.transcribe_file(system_path)  # type: ignore[arg-type]
            # Mic is you; keep it a single "You" speaker. Diarize only the system track.
            tracks.append((label or "You", _color(0), mic_lines))
            tracks.extend(
                await self._speaker_groups(
                    system_path, sys_lines, base_idx=1, single_label="Others", use_diar=use_diar  # type: ignore[arg-type]
                )
            )
        else:
            log.info("transcribing recording %d (single track)", recording_id)
            lines, language = await self._whisper.transcribe_file(audio_path)
            tracks.extend(
                await self._speaker_groups(
                    audio_path, lines, base_idx=0, single_label=(label or "Speaker 1"), use_diar=use_diar
                )
            )

        total = 0
        with Session(engine) as s:
            # Idempotent: clear any prior speakers/segments from a previous attempt.
            s.exec(delete(Segment).where(Segment.recording_id == recording_id))  # type: ignore[arg-type]
            s.exec(delete(Speaker).where(Speaker.recording_id == recording_id))  # type: ignore[arg-type]
            for speaker_label, color, lines in tracks:
                speaker = Speaker(recording_id=recording_id, label=speaker_label, color=color)
                s.add(speaker)
                s.flush()  # assign speaker.id
                for line in lines:
                    s.add(
                        Segment(
                            recording_id=recording_id,
                            speaker_id=speaker.id,
                            start_ts=line.start,
                            end_ts=line.end,
                            text=line.text,
                        )
                    )
                    total += 1
            rec = s.get(Recording, recording_id)
            if rec is not None:
                rec.language = language  # keep status `processing` until summary is attempted
                s.add(rec)
            s.commit()
        lines_present = total > 0
        log.info("recording %d transcribed (%d segments, lang=%s)", recording_id, total, language)

        # Auto-generate the default summary BEFORE flipping to `ready`, so that
        # `ready` means transcript + summary are both present and the UI shows
        # them together. Best-effort: a summary failure must not fail the recording.
        if lines_present and self._pipeline is not None:
            try:
                tmpl_id = self._pipeline.default_summary_template_id()
                if tmpl_id is not None:
                    await self._pipeline.summarize(recording_id=recording_id, template_id=tmpl_id)
                    log.info("recording %d auto-summary generated", recording_id)
            except Exception:
                log.exception("auto-summary failed for recording %d (transcript intact)", recording_id)

        with Session(engine) as s:
            rec = s.get(Recording, recording_id)
            if rec is not None:
                rec.status = "ready"
                rec.error = None
                s.add(rec)
                s.commit()
        log.info("recording %d ready", recording_id)

    async def _speaker_groups(
        self,
        path: str,
        lines: list,
        base_idx: int,
        single_label: str,
        use_diar: bool,
    ) -> list[tuple[str, str, list]]:
        """Return (label, color, lines) groups for a track. With diarization enabled,
        split the track into Speaker 1..N by cluster; otherwise a single group.
        Any diarization failure falls back to the single-group baseline."""
        if not use_diar or not lines:
            return [(single_label, _color(base_idx), lines)]
        try:
            assert self._diarizer is not None
            turns = await self._diarizer.diarize(path)
            if not turns:
                return [(single_label, _color(base_idx), lines)]
            # Word-level re-segmentation: a single whisper line can span a speaker
            # change, so assign at word granularity and regroup by speaker.
            cluster_lines = diarize_lines(lines, turns)
            order: list[str] = []
            by_cluster: dict[str, list] = {}
            for cluster, tline in cluster_lines:
                if cluster not in by_cluster:
                    by_cluster[cluster] = []
                    order.append(cluster)
                by_cluster[cluster].append(tline)
            log.info("diarization split %s into %d speaker(s)", Path(path).name, len(order))
            return [
                (f"Speaker {i + 1}", _color(base_idx + i), by_cluster[c])
                for i, c in enumerate(order)
            ]
        except Exception:
            log.exception("diarization failed for %s; falling back to baseline split", Path(path).name)
            return [(single_label, _color(base_idx), lines)]

    def _mark_failed(self, recording_id: int, message: str) -> None:
        with Session(engine) as s:
            rec = s.get(Recording, recording_id)
            if rec is not None:
                rec.status = "failed"
                rec.error = message
                s.add(rec)
                s.commit()
