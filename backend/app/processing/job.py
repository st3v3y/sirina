"""Background transcription processor: one job at a time, restart-safe.

Pulls recording ids off a queue, transcribes the recording's audio with the
offline-quality whisper path, writes Segment rows, and flips the recording to
`ready` (or `failed`).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlmodel import Session, delete, select

from ..db import engine
from ..models import Recording, Segment
from ..transcribe.whisper import FasterWhisperWorker

log = logging.getLogger(__name__)


class TranscriptionProcessor:
    def __init__(self, whisper: FasterWhisperWorker) -> None:
        self._whisper = whisper
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

        if not audio_path or not Path(audio_path).exists():
            self._mark_failed(recording_id, "audio file missing")
            return

        await self._whisper.load()
        log.info("transcribing recording %d (%s)", recording_id, Path(audio_path).name)
        lines, language = await self._whisper.transcribe_file(audio_path)

        with Session(engine) as s:
            # Idempotent: clear any partial segments from a previous attempt.
            s.exec(delete(Segment).where(Segment.recording_id == recording_id))  # type: ignore[arg-type]
            for start, end, text in lines:
                s.add(
                    Segment(
                        recording_id=recording_id,
                        speaker_label="Speaker 1",  # real speakers come in speakers-and-people
                        start_ts=start,
                        end_ts=end,
                        text=text,
                    )
                )
            rec = s.get(Recording, recording_id)
            if rec is not None:
                rec.language = language
                rec.status = "ready"
                rec.error = None
                s.add(rec)
            s.commit()
        log.info("recording %d ready (%d segments, lang=%s)", recording_id, len(lines), language)

    def _mark_failed(self, recording_id: int, message: str) -> None:
        with Session(engine) as s:
            rec = s.get(Recording, recording_id)
            if rec is not None:
                rec.status = "failed"
                rec.error = message
                s.add(rec)
                s.commit()
