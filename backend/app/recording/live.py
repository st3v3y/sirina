"""Transcription during recording (opt-in per recording, WhisperKit only).

While a call runs, complete ~3-minute windows are finalized exactly as the post-stop job
would (same `finalize_range`, same speaker rows), so after stop only the last minutes,
speaker splitting and the summary remain. WhisperKit runs mostly on the Neural Engine
(~17 CPU-s per 10 min of audio, 0.4 GB), so the call isn't slowed; the CPU engine is
never used here. Pauses while Low Power Mode is on and catches up afterwards.

Stop safety: commits happen under a lock; `stop()` takes that lock and sets a flag first,
so no window can commit after the recording has stopped (an in-flight window is simply
transcribed again by the job).
"""
from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable

from ..audio.power import power_state
from ..config import settings
from ..db import engine as db_engine
from ..processing.windows import Track, commit_window, finalize_range, final_lines_by_label

log = logging.getLogger(__name__)

POLL_S = 15.0
DIARIZE_EVERY_S = 600.0  # with diarization_timing == "during_recording"


class LiveFinalizer:
    def __init__(
        self,
        recording_id: int,
        tracks: list[Track],
        recorded_s: Callable[[], float],
        transcribe: Callable,
        *,
        diarize: Callable[[float], "asyncio.Future | None"] | None = None,
        poll_s: float = POLL_S,
        target_s: float | None = None,
        low_power: Callable[[], bool] | None = None,
    ) -> None:
        self.recording_id = recording_id
        self.tracks = tracks
        self._recorded_s = recorded_s  # seconds safely on disk in EVERY track
        self._transcribe = transcribe  # engine.transcribe_window-compatible
        self._diarize = diarize
        self._poll_s = poll_s
        self._target_s = float(target_s if target_s is not None else settings.transcribe_chunk_seconds)
        self._low_power = low_power or (lambda: bool(power_state().get("low_power")))
        self.final_until_s = 0.0
        self.paused: str | None = None  # "low_power" while paused
        self.enabled = True  # toggled from the recording screen
        self.failed: str | None = None
        self._language: str | None = settings.whisper_language or None
        self._last_diarized_s = 0.0
        self._commit_lock = threading.Lock()
        self._stopped = False
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"live-finalizer-{self.recording_id}")

    def _commit(self, db, rid, a, b, lines_by_track, language) -> int:
        with self._commit_lock:
            if self._stopped:
                return 0  # recording stopped: the job redoes this window
            return commit_window(db, rid, a, b, lines_by_track, language)

    def _should_stop(self) -> bool:
        return self._stopped or not self.enabled or self._low_power()

    async def _run(self) -> None:
        while not self._stopped:
            await asyncio.sleep(self._poll_s)
            if not self.enabled:
                continue
            if self._low_power():
                self.paused = "low_power"
                continue
            self.paused = None
            try:
                await self._step()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # never harms the recording; the job finishes the rest
                self.failed = f"{type(e).__name__}: {e}"
                log.exception("live transcription stopped for recording %d", self.recording_id)
                return

    async def _step(self) -> None:
        available = self._recorded_s() - 2.0  # stay behind the write head
        # Only complete windows are committed; wait until more than 1.5 windows are on disk.
        if available - self.final_until_s <= self._target_s * 1.5:
            return

        def on_window(b: float) -> None:
            self.final_until_s = b

        self._language, _ = await finalize_range(
            db_engine=db_engine,
            recording_id=self.recording_id,
            tracks=self.tracks,
            from_s=self.final_until_s,
            to_s=available,
            target_s=self._target_s,
            transcribe=self._transcribe,
            language=self._language,
            should_stop=self._should_stop,
            on_window=on_window,
            include_tail=False,
            commit=self._commit,
        )
        if self._diarize and self.final_until_s - self._last_diarized_s >= DIARIZE_EVERY_S and not self._stopped:
            self._last_diarized_s = self.final_until_s
            await self._diarize(self.final_until_s)

    async def stop(self) -> None:
        """Stop for good. After this returns no live window can commit."""
        with self._commit_lock:
            self._stopped = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    def snapshot(self) -> dict:
        return {
            "final_until_s": self.final_until_s,
            "paused": self.paused,
            "enabled": self.enabled,
            "failed": self.failed,
        }


def lines_so_far(recording_id: int):
    """Final lines by speaker label (with words) — input for a during-recording split."""
    return final_lines_by_label(db_engine, recording_id)
