"""Background transcription processor: one job at a time, restart-safe.

Pulls recording ids off a queue, transcribes the recording's audio with the
offline-quality whisper path, writes Segment rows, and flips the recording to
`ready` (or `failed`).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from sqlmodel import Session, delete, select

from ..config import settings
from ..db import engine
from ..models import Recording, Segment, Speaker
from ..speakers import SELF_LABEL, get_or_create_self_person
from ..transcribe.whisper import FasterWhisperWorker
from ..voiceprints import match_speakers
from ..audio.power import power_guard, power_note, power_state
from .compress import compress_recording, restore_wavs
from .diarize import VOICEPRINT_MODEL, Diarizer, diarize_lines
from .segment import resegment_lines
from .windows import Track, final_lines_by_label, finalize_range, insert_drafts, tracks_for

if TYPE_CHECKING:
    from ..pipeline import Pipeline

log = logging.getLogger(__name__)

# Stable colour tokens assigned to speakers in creation order; the frontend maps
# each token to a palette.
_SPEAKER_COLORS = ["sky", "emerald", "violet", "amber", "rose", "teal"]


def _color(i: int) -> str:
    return _SPEAKER_COLORS[i % len(_SPEAKER_COLORS)]


def _is_silent(path: str) -> bool:
    """True if the track's peak amplitude is below the silence threshold. Used to skip
    transcribing empty tracks (e.g. a system/BlackHole capture with nothing playing),
    which otherwise make Whisper hallucinate phrases on the silence."""
    threshold = settings.silence_peak_threshold
    if threshold <= 0:
        return False
    try:
        import wave

        import numpy as np

        with wave.open(path, "rb") as w:
            sr = w.getframerate() or 16000
            peak = 0
            block = sr * 30  # 30 s blocks → bounded memory on long files
            while True:
                raw = w.readframes(block)
                if not raw:
                    break
                arr = np.frombuffer(raw, dtype=np.int16)
                if arr.size:
                    peak = max(peak, int(np.abs(arr).max()))
        return (peak / 32768.0) < threshold
    except Exception:
        log.debug("silence check failed for %s; transcribing anyway", path, exc_info=True)
        return False


# Diarization can emit a brief room-noise / cross-talk cluster that would otherwise
# surface as a phantom "Speaker N". Drop clusters below both an absolute speech floor
# and a share of the track, merging their lines into the dominant kept speaker so no
# transcript text is lost. At least one speaker always remains.
# The share floor is deliberately small: in a long meeting a real third participant may
# speak only a couple of minutes (well under 5% of the total), and a 5% gate merged them
# away into another speaker. The absolute-seconds floor still removes genuine noise blips.
_CLUSTER_MIN_SECONDS = 2.0
_CLUSTER_MIN_SHARE = 0.015


def _prune_clusters(order: list[str], by_cluster: dict[str, list]) -> list[str]:
    def dur(cluster: str) -> float:
        return sum(max(0.0, ln.end - ln.start) for ln in by_cluster[cluster])

    durations = {c: dur(c) for c in order}
    total = sum(durations.values())
    if total <= 0 or len(order) <= 1:
        return order
    threshold = max(_CLUSTER_MIN_SECONDS, _CLUSTER_MIN_SHARE * total)
    kept = [c for c in order if durations[c] >= threshold]
    if not kept:
        kept = [max(order, key=lambda c: durations[c])]
    if len(kept) == len(order):
        return order
    dominant = max(kept, key=lambda c: durations[c])
    for c in order:
        if c not in kept:
            by_cluster[dominant].extend(by_cluster[c])
            del by_cluster[c]
    by_cluster[dominant].sort(key=lambda ln: ln.start)
    return [c for c in order if c in kept]


# A genuine participant can rack up overlap by backchanneling ("mm-hm") during the
# user's monologues, so a cluster is only treated as echo when it is ALSO a small share
# of the track — a real speaker's own contributions push them past this cap.
_ECHO_MAX_SHARE = 0.25


def _overlap_seconds(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    """Total seconds where intervals of (sorted) `a` overlap intervals of (sorted) `b`."""
    total = 0.0
    j = 0
    for start, end in a:
        while j < len(b) and b[j][1] <= start:
            j += 1
        k = j
        while k < len(b) and b[k][0] < end:
            total += max(0.0, min(end, b[k][1]) - max(start, b[k][0]))
            k += 1
    return total


def _is_echo_cluster(lines: list, mic_lines: list, track_total: float) -> bool:
    """True if this system-track cluster is the user's own echo: its speech coincides
    almost entirely with the mic ("You") speech and it's a minor share of the track.
    The echo consists of fragmentary duplicates of words the mic already captured."""
    threshold = settings.echo_speaker_overlap
    if threshold <= 0 or not mic_lines or not lines:
        return False
    duration = sum(max(0.0, ln.end - ln.start) for ln in lines)
    if duration <= 0:
        return False
    if track_total > 0 and duration / track_total > _ECHO_MAX_SHARE:
        return False
    mine = sorted((ln.start, ln.end) for ln in lines)
    mic = sorted((ln.start, ln.end) for ln in mic_lines)
    return _overlap_seconds(mine, mic) / duration >= threshold


def _tracks_duration(tracks: list[Track]) -> float:
    """Longest track length in seconds (0 when unreadable)."""
    from ..audio.wav import wav_duration_s

    best = 0.0
    for t in tracks:
        try:
            best = max(best, wav_duration_s(t.path))
        except Exception:
            log.debug("could not read duration of %s", t.path, exc_info=True)
    return best


def _has_drafts_after(recording_id: int, after_s: float) -> bool:
    with Session(engine) as s:
        return s.exec(
            select(Segment.id).where(
                Segment.recording_id == recording_id,
                Segment.is_draft == True,  # noqa: E712
                Segment.start_ts >= after_s,
            )
        ).first() is not None


class TranscriptionProcessor:
    def __init__(
        self,
        whisper: FasterWhisperWorker,
        pipeline: "Pipeline | None" = None,
        diarizer: Diarizer | None = None,
        drafter=None,
    ) -> None:
        self._whisper = whisper
        # Optional fast on-device draft pass: async (path, start_s, end_s, language) -> [TLine].
        self._drafter = drafter
        # CPU engine used for a job when WhisperKit can't start or keeps failing.
        self._fallback: FasterWhisperWorker | None = None
        # Why this recording used another engine (surfaced like the diarization note).
        self._engine_note: dict[int, str] = {}
        # Recording time up to which the transcript is final (mirrors the DB column).
        self._final_until: dict[int, float] = {}
        self._pipeline = pipeline
        self._diarizer = diarizer
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        # Ids currently sitting in the queue — enqueue() dedupes against this (and the
        # running job), so a double "Re-process" click can't run the job twice.
        self._pending: set[int] = set()
        self._task: asyncio.Task | None = None
        # In-memory, ephemeral per-recording progress and start time (monotonic).
        self._progress: dict[int, dict] = {}
        self._started: dict[int, float] = {}
        # The recording currently being processed (None when idle). Used to gate a
        # transcription-engine reload — swapping the model mid-job would corrupt it.
        self._current_id: int | None = None
        # Recordings whose diarization the user asked to cancel (fall back to baseline).
        self._cancel_diar: set[int] = set()
        # Recordings the user asked to stop processing entirely (keep any transcript so far).
        self._cancel_processing: set[int] = set()
        # A per-recording note explaining why speaker splitting didn't run (surfaced to the
        # user as a warning, so "only You + Speaker 1" isn't a silent mystery).
        self._diar_note: dict[int, str] = {}

    def is_busy(self) -> bool:
        """True while a recording is actively being processed."""
        return self._current_id is not None

    def current_id(self) -> int | None:
        """The recording being processed right now, or None when idle."""
        return self._current_id

    def set_engine(self, whisper: FasterWhisperWorker) -> None:
        """Swap the transcription engine (used by the Settings reload action). Only safe
        when idle — the caller checks `is_busy()` first."""
        self._whisper = whisper

    def progress_for(self, recording_id: int) -> dict | None:
        e = self._progress.get(recording_id)
        if e is None:
            return None
        now = time.monotonic()
        elapsed = now - self._started.get(recording_id, now)
        fraction = e["fraction"]
        estimated = False
        # Engines without a measured fraction: estimate one from elapsed time vs an
        # estimate, capped below 1.0 so it never claims "done" early.
        if fraction is None and e.get("est_total"):
            est = e["est_total"]
            grown = (now - e.get("stage_started", now)) / est if est > 0 else 0.0
            fraction = min(0.95, max(0.0, grown))
            estimated = True
        return {
            "stage": e["stage"],
            "fraction": fraction,
            "elapsed_s": round(elapsed, 1),
            "estimated": estimated,
            "power_note": power_note(power_state()),
            "final_until_s": self._final_until.get(recording_id),
        }

    def _set_progress(
        self, recording_id: int, stage: str, fraction: float | None = None, *, est_total: float | None = None
    ) -> None:
        self._progress[recording_id] = {
            "stage": stage,
            "fraction": fraction,
            "est_total": est_total,
            "stage_started": time.monotonic(),
        }
        if settings.dev:
            log.debug(
                "progress[%s] stage=%s fraction=%s est_total=%s", recording_id, stage, fraction, est_total
            )

    def _progress_cb(self, recording_id: int, lo: float, hi: float):
        """Build a transcribe progress callback mapping a track's (done,total) into [lo,hi]."""
        def cb(done: float, total: float) -> None:
            frac = lo + (hi - lo) * (done / total if total > 0 else 0.0)
            self._set_progress(recording_id, "transcribing", min(hi, max(lo, frac)))
        return cb

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="transcription-processor")

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def enqueue(self, recording_id: int) -> None:
        if recording_id in self._pending or recording_id == self._current_id:
            log.info("recording %d already queued/processing; skipping enqueue", recording_id)
            return
        self._pending.add(recording_id)
        self._set_progress(recording_id, "queued", None)
        power_guard.hold(("job", recording_id))  # released when the job ends (see _run)
        await self._queue.put(recording_id)

    async def requeue_pending(self) -> None:
        """Re-enqueue any recordings left in `processing` (e.g. after a restart). Recordings
        held awaiting a trim decision (pending_trim set) are skipped — they stay held so the
        prompt survives a restart instead of the dead air being transcribed anyway."""
        with Session(engine) as s:
            ids = s.exec(
                select(Recording.id).where(
                    Recording.status == "processing",
                    Recording.pending_trim == None,  # noqa: E711
                )
            ).all()  # type: ignore[arg-type]
        for rid in ids:
            if rid is not None:
                power_guard.hold(("job", rid))
                await self._queue.put(rid)
        if ids:
            log.info("re-enqueued %d pending recording(s) for transcription", len(ids))

    async def _run(self) -> None:
        while True:
            recording_id = await self._queue.get()
            self._current_id = recording_id
            self._pending.discard(recording_id)  # after _current_id is set — no dedupe gap
            try:
                await self._process(recording_id)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.exception("transcription job failed for recording %d", recording_id)
                self._mark_failed(recording_id, f"{type(e).__name__}: {e}"[:500])
            finally:
                self._current_id = None
                # Progress is ephemeral: drop it once the job ends (ready/failed).
                self._progress.pop(recording_id, None)
                self._started.pop(recording_id, None)
                self._cancel_diar.discard(recording_id)
                self._cancel_processing.discard(recording_id)
                self._diar_note.pop(recording_id, None)
                self._engine_note.pop(recording_id, None)
                self._final_until.pop(recording_id, None)
                power_guard.release(("job", recording_id))
                self._queue.task_done()

    async def _process(self, recording_id: int) -> None:
        self._started[recording_id] = time.monotonic()
        # Stopped while still queued — don't even start the (uninterruptible) transcription.
        if self._processing_cancelled(recording_id):
            self._mark_failed(recording_id, "Processing stopped")
            return
        with Session(engine) as s:
            rec = s.get(Recording, recording_id)
            if rec is None:
                return
            audio_path = rec.audio_path
            mic_path = rec.mic_path
            system_path = rec.system_path
            duration_s = rec.duration_s or 0.0

        # Compressed (.m4a) tracks must be decoded back to WAV before anything reads
        # them — the transcription/diarization/silence stack is PCM-WAV-only. Doing it
        # here (not in the reprocess endpoint) means it is serialized with the job and
        # also covers a crash that left a recording half-compressed.
        if any((p or "").lower().endswith(".m4a") for p in (audio_path, mic_path, system_path)):
            self._set_progress(recording_id, "queued", None)
            if not await asyncio.to_thread(restore_wavs, recording_id, engine):
                self._mark_failed(recording_id, "couldn't decode this recording's compressed audio")
                return
            with Session(engine) as s:
                rec = s.get(Recording, recording_id)
                if rec is None:
                    return
                audio_path = rec.audio_path
                mic_path = rec.mic_path
                system_path = rec.system_path

        if not audio_path or not Path(audio_path).exists():
            self._mark_failed(recording_id, "audio file missing")
            return

        two_track = bool(mic_path and system_path and Path(mic_path).exists() and Path(system_path).exists())
        use_diar = self._diarizer is not None and self._diarizer.is_available()
        engine_ = await self._ready_engine(recording_id)
        if settings.dev:
            log.debug(
                "processing recording %d: engine=%s two_track=%s diar=%s duration=%.1fs",
                recording_id, getattr(engine_, "name", "?"), two_track, use_diar, duration_s,
            )

        # 1) Which tracks to transcribe. Silent tracks are skipped: a silent system/BlackHole
        #    capture would otherwise make the model hallucinate captions on the silence.
        tracks: list[Track] = []
        all_tracks = tracks_for(mic_path, system_path, audio_path, _color) if two_track else tracks_for(None, None, audio_path, _color)
        for t in all_tracks:
            if _is_silent(t.path):
                log.info("recording %d: %s track is silent — skipping", recording_id, t.name)
            else:
                tracks.append(t)
        log.info("transcribing recording %d (%s; %d non-silent track(s))",
                 recording_id, "two-track" if two_track else "single track", len(tracks))

        total_s = _tracks_duration(tracks) or duration_s
        with Session(engine) as s:
            rec = s.get(Recording, recording_id)
            start_from = float(rec.final_until_s or 0.0) if rec is not None else 0.0
            language: str | None = rec.language if rec is not None and start_from > 0 else None
        if start_from > 0:
            log.info("recording %d: resuming after %.1fs already final", recording_id, start_from)
            self._final_until[recording_id] = start_from

        # 2) A fast on-device draft of whatever isn't final yet, so there is something to
        #    read right away (skipped when captions already left drafts there).
        if tracks and self._drafter is not None and start_from < total_s and not _has_drafts_after(recording_id, start_from):
            self._set_progress(recording_id, "drafting", None)
            await self._draft(recording_id, tracks, start_from, total_s)

        # 3) Final transcript, window by window; each window replaces its draft lines.
        def _on_window(b: float) -> None:
            self._final_until[recording_id] = b
            span = total_s - start_from
            self._set_progress(recording_id, "transcribing", min(1.0, (b - start_from) / span) if span > 0 else 1.0)

        self._set_progress(recording_id, "transcribing", 0.0)
        language, _ = await finalize_range(
            db_engine=engine,
            recording_id=recording_id,
            tracks=tracks,
            from_s=start_from,
            to_s=total_s,
            target_s=float(settings.transcribe_chunk_seconds),
            transcribe=self._transcribe_with_fallback(recording_id, engine_),
            language=language or (settings.whisper_language or None),
            should_stop=lambda: self._processing_cancelled(recording_id),
            on_window=_on_window,
        )

        by_label = await asyncio.to_thread(final_lines_by_label, engine, recording_id)
        # The other side may already be split into Speaker 1..N (speaker splitting during
        # the recording); the final split always starts from all of its lines.
        others = sorted(
            (ln for label, ls in by_label.items() if label != "You" for ln in ls), key=lambda ln: ln.start
        )
        mic_lines = by_label.get("You", []) if two_track else []
        sys_lines = others if two_track else []
        lines = [] if two_track else others
        lines_present = any(by_label.values())
        log.info("recording %d transcribed (%d lines, lang=%s)", recording_id,
                 sum(len(v) for v in by_label.values()), language)

        # 3) Diarization (optional): refine speakers and replace the baseline. Only when
        #    there's a non-silent system/single track to diarize. The user can cancel it;
        #    on cancel we stop waiting and keep the baseline split.
        diar_target = bool(sys_lines) if two_track else bool(lines)
        if use_diar and lines_present and diar_target and not self._diar_cancelled(recording_id):
            self._set_progress(recording_id, "diarizing", None)

            async def _compute_diarized() -> tuple[list[tuple[str, str, list]], dict[str, list[float]]]:
                if two_track:
                    groups: list[tuple[str, str, list]] = []
                    if mic_lines:
                        groups.append(("You", _color(0), mic_lines))
                    sys_groups, embeddings = await self._speaker_groups(
                        system_path, sys_lines, base_idx=1, single_label="Speaker 1", use_diar=True,  # type: ignore[arg-type]
                        recording_id=recording_id,
                        # Suppress the user's own echo in the call audio. Compare against
                        # word-bounded mic lines: raw segment spans can cover long silences.
                        echo_ref=resegment_lines(mic_lines),
                    )
                    groups.extend(sys_groups)
                    return groups, embeddings
                return await self._speaker_groups(
                    audio_path, lines, base_idx=0, single_label="Speaker 1", use_diar=True,
                    recording_id=recording_id,
                )

            # pyannote runs as one blocking executor call and can't be preempted, so we
            # race it against the cancel flag: on cancel we abandon the result (the
            # orphaned pass finishes in the background and is discarded) and keep baseline.
            diar_task = asyncio.create_task(_compute_diarized())
            while not diar_task.done() and not self._diar_cancelled(recording_id):
                await asyncio.sleep(0.5)
            if self._diar_cancelled(recording_id):
                def _swallow(t: asyncio.Task) -> None:
                    try:
                        t.exception()
                    except Exception:
                        pass
                diar_task.add_done_callback(_swallow)
                log.info("recording %d diarization cancelled; keeping baseline split", recording_id)
            else:
                diar_groups, diar_embeddings = await diar_task
                await asyncio.to_thread(
                    self._write_tracks, recording_id, diar_groups, language,
                    embeddings=diar_embeddings,
                )
                log.info("recording %d diarized", recording_id)

        # Best-effort: try to auto-link this recording's speakers to known People.
        # No-op for now (voice fingerprinting is a future change); never creates People.
        if lines_present:
            self._match_speakers_to_people(recording_id)

        # Auto-generate the default summary BEFORE flipping to `ready`, so that
        # `ready` means transcript + summary are both present and the UI shows
        # them together. Best-effort: a summary failure must not fail the recording.
        if lines_present and self._pipeline is not None and not self._processing_cancelled(recording_id):
            try:
                tmpl_id = self._pipeline.default_summary_template_id()
                if tmpl_id is not None:
                    self._set_progress(recording_id, "summarizing", None)
                    await self._pipeline.summarize(recording_id=recording_id, template_id=tmpl_id)
                    log.info("recording %d auto-summary generated", recording_id)
            except Exception:
                log.exception("auto-summary failed for recording %d (transcript intact)", recording_id)

        # Shrink the audio (WAV → AAC) BEFORE flipping to `ready`: while the status is
        # `processing`, the delete/reprocess endpoints are blocked, so compression can't
        # race them. The transcript/summary are already persisted and visible by now.
        # Best-effort: a failure just keeps the WAVs.
        if settings.compress_audio:
            try:
                self._set_progress(recording_id, "compressing", None)
                await asyncio.to_thread(compress_recording, recording_id, engine)
            except Exception:
                log.exception("audio compression failed for recording %d (WAVs kept)", recording_id)

        self._set_progress(recording_id, "done", 1.0)

        diar_note = " ".join(
            n for n in (self._engine_note.pop(recording_id, None), self._diar_note.pop(recording_id, None)) if n
        ) or None
        with Session(engine) as s:
            rec = s.get(Recording, recording_id)
            if rec is not None:
                rec.status = "ready"
                rec.error = None
                # Surface a diarization failure so a lone "Speaker 1" isn't a silent mystery.
                # Don't clobber a capture warning already on the recording — append to it.
                if diar_note:
                    rec.warning = f"{rec.warning} {diar_note}".strip() if rec.warning else diar_note
                s.add(rec)
                s.commit()
        log.info("recording %d ready", recording_id)

    async def split_speakers_live(
        self, recording_id: int, two_track: bool, mic_path: str | None, system_path: str | None
    ) -> None:
        """Speaker splitting during the recording (diarization_timing == "during_recording"):
        split everything final so far and relabel it. Provisional — new windows keep landing
        on "Speaker 1" until the next run, and the split after stop is authoritative."""
        if self._diarizer is None or not self._diarizer.is_available():
            return
        by_label = await asyncio.to_thread(final_lines_by_label, engine, recording_id)
        others = sorted((ln for lb, ls in by_label.items() if lb != "You" for ln in ls), key=lambda ln: ln.start)
        if not others:
            return
        mic_lines = by_label.get("You", []) if two_track else []
        path = system_path if two_track else (mic_path or system_path)
        groups, embeddings = await self._speaker_groups(
            path, others, base_idx=1 if two_track else 0, single_label="Speaker 1", use_diar=True,  # type: ignore[arg-type]
            recording_id=recording_id, echo_ref=mic_lines or None,
        )
        if two_track and mic_lines:
            groups = [("You", _color(0), mic_lines), *groups]
        with Session(engine) as s:
            rec = s.get(Recording, recording_id)
            language = rec.language if rec else None
        await asyncio.to_thread(self._write_tracks, recording_id, groups, language, embeddings=embeddings)
        log.info("recording %d: speakers split during recording (%d groups)", recording_id, len(groups))

    async def _ready_engine(self, recording_id: int):
        """The loaded engine for this job. A WhisperKit model that can't be downloaded or
        prepared falls back to the CPU engine for this job (with a note), instead of
        failing the recording."""
        eng = self._whisper
        if eng.is_loaded():
            return eng
        is_wk = getattr(eng, "name", "") == "whisperkit"
        if is_wk:
            self._set_progress(recording_id, "preparing_model", None)
        try:
            await eng.load()
            return eng
        except Exception as e:
            if not is_wk:
                raise
            log.exception("WhisperKit unavailable for recording %d; using the CPU engine", recording_id)
            self._engine_note[recording_id] = (
                f"The fast transcription model couldn't be prepared ({type(e).__name__}), so this "
                "recording used the slower CPU engine. Check Settings → Speech models."
            )
            return await self._cpu_fallback()

    async def _cpu_fallback(self) -> FasterWhisperWorker:
        if self._fallback is None:
            self._fallback = FasterWhisperWorker()
        await self._fallback.load()
        return self._fallback

    def _transcribe_with_fallback(self, recording_id: int, eng):
        """`transcribe_window` that switches to the CPU engine for the remaining windows if
        the speech helper fails twice in a row (it already restarts itself once)."""
        from ..transcribe.speech_helper import HelperError

        state = {"engine": eng}

        async def transcribe(path: str, start_s: float, end_s: float | None, *, language: str | None = None):
            try:
                return await state["engine"].transcribe_window(path, start_s, end_s, language=language)
            except HelperError as e:
                if state["engine"] is not eng or getattr(eng, "name", "") != "whisperkit":
                    raise
                log.warning("speech helper failed on recording %d (%s); CPU engine for the rest", recording_id, e)
                self._engine_note[recording_id] = (
                    "The fast transcription engine stopped working mid-way, so the rest of this "
                    "recording used the slower CPU engine."
                )
                state["engine"] = await self._cpu_fallback()
                return await state["engine"].transcribe_window(path, start_s, end_s, language=language)

        return transcribe

    async def _draft(self, recording_id: int, tracks: list[Track], from_s: float, to_s: float) -> None:
        """Best-effort fast draft of [from_s, to_s) for every track; never fails the job."""
        lang = settings.whisper_language or None
        for track in tracks:
            try:
                lines = await self._drafter(track.path, from_s, to_s, lang)
                await asyncio.to_thread(insert_drafts, engine, recording_id, [(track, lines)], from_s)
            except Exception:
                log.warning("draft pass failed for %s of recording %d", track.name, recording_id, exc_info=True)

    def _write_tracks(
        self,
        recording_id: int,
        tracks: list[tuple[str, str, list]],
        language: str | None,
        embeddings: dict[str, list[float]] | None = None,
    ) -> int:
        """Replace a recording's speakers/segments with `tracks` (idempotent clear-then-write).
        `embeddings` maps a track label to its diarization voice embedding, stored on the
        Speaker row for cross-recording person matching. Returns the number of segments written."""
        total = 0
        with Session(engine) as s:
            s.exec(delete(Segment).where(Segment.recording_id == recording_id))  # type: ignore[arg-type]
            s.exec(delete(Speaker).where(Speaker.recording_id == recording_id))  # type: ignore[arg-type]
            self_person_id: int | None = None
            for speaker_label, color, lines in tracks:
                embedding = (embeddings or {}).get(speaker_label)
                speaker = Speaker(
                    recording_id=recording_id,
                    label=speaker_label,
                    color=color,
                    embedding=json.dumps(embedding) if embedding else None,
                    embedding_model=VOICEPRINT_MODEL if embedding else None,
                )
                # Bind the mic ("You") speaker to the singleton self-Person so the app user
                # shows up in People and a rename of "You" propagates everywhere.
                if speaker_label == SELF_LABEL:
                    if self_person_id is None:
                        self_person_id = get_or_create_self_person(s).id
                    speaker.person_id = self_person_id
                s.add(speaker)
                s.flush()  # assign speaker.id
                # Break long monologue-sized lines into turns/sentences so the two tracks
                # interleave by timestamp into a readable back-and-forth (see segment.py).
                for line in resegment_lines(lines):
                    s.add(
                        Segment(
                            recording_id=recording_id,
                            speaker_id=speaker.id,
                            start_ts=line.start,
                            end_ts=line.end,
                            text=line.text,
                            words=json.dumps([[round(a, 3), round(b, 3), t] for (a, b, t) in line.words])
                            if line.words else None,
                        )
                    )
                    total += 1
            rec = s.get(Recording, recording_id)
            if rec is not None:
                rec.language = language  # keep status `processing` until summary is attempted
                s.add(rec)
            s.commit()
        return total

    def cancel_diarization(self, recording_id: int) -> None:
        """Request that diarization for this recording be skipped (baseline split kept)."""
        self._cancel_diar.add(recording_id)

    def _diar_cancelled(self, recording_id: int) -> bool:
        # A full stop also short-circuits the diarization wait.
        return recording_id in self._cancel_diar or recording_id in self._cancel_processing

    def cancel_processing(self, recording_id: int) -> None:
        """Request that processing stop after the current uninterruptible step. Any transcript
        already written is kept (the recording finalizes as `ready`); the remaining stages
        (diarization, summary) are skipped. Checked at stage boundaries — it cannot preempt a
        transcription already running in the executor, but stops everything after it."""
        self._cancel_processing.add(recording_id)

    def _processing_cancelled(self, recording_id: int) -> bool:
        return recording_id in self._cancel_processing

    async def _speaker_groups(
        self,
        path: str,
        lines: list,
        base_idx: int,
        single_label: str,
        use_diar: bool,
        recording_id: int | None = None,
        echo_ref: list | None = None,
    ) -> tuple[list[tuple[str, str, list]], dict[str, list[float]]]:
        """Return (label, color, lines) groups for a track plus a label -> voice-embedding
        map. With diarization enabled, split the track into Speaker 1..N by cluster;
        otherwise a single group. Clusters that are just the user's echo (speech that
        coincides with `echo_ref`, the mic lines) are dropped. Any diarization failure
        falls back to the single-group baseline (and records a note on `recording_id`
        so the user learns why speakers weren't separated)."""
        if not use_diar or not lines:
            return [(single_label, _color(base_idx), lines)], {}
        try:
            assert self._diarizer is not None
            result = await self._diarizer.diarize(path)
            # Test doubles may return a bare turn list; the real Diarizer returns a
            # DiarizationResult with per-cluster embeddings (SpeakerKit centroids).
            turns = getattr(result, "turns", result)
            cluster_embeddings: dict[str, list[float]] = getattr(result, "embeddings", {}) or {}
            if not turns:
                return [(single_label, _color(base_idx), lines)], {}

            # Word-level re-segmentation: a single whisper line can span a speaker
            # change, so assign at word granularity and regroup by speaker. On a long
            # meeting this is real CPU work — run it off the event loop.
            def _regroup() -> tuple[list[str], dict[str, list]]:
                cluster_lines = diarize_lines(lines, turns)
                order: list[str] = []
                by_cluster: dict[str, list] = {}
                for cluster, tline in cluster_lines:
                    if cluster not in by_cluster:
                        by_cluster[cluster] = []
                        order.append(cluster)
                    by_cluster[cluster].append(tline)
                return _prune_clusters(order, by_cluster), by_cluster

            order, by_cluster = await asyncio.to_thread(_regroup)
            if echo_ref:
                track_total = sum(
                    max(0.0, ln.end - ln.start) for c in order for ln in by_cluster[c]
                )
                kept = []
                for c in order:
                    if _is_echo_cluster(by_cluster[c], echo_ref, track_total):
                        log.info(
                            "dropping echo speaker on %s (%.0fs coinciding with the mic)",
                            Path(path).name,
                            sum(max(0.0, ln.end - ln.start) for ln in by_cluster[c]),
                        )
                    else:
                        kept.append(c)
                order = kept
            log.info("diarization split %s into %d speaker(s)", Path(path).name, len(order))
            groups = [
                (f"Speaker {i + 1}", _color(base_idx + i), by_cluster[c])
                for i, c in enumerate(order)
            ]
            embeddings = {
                f"Speaker {i + 1}": cluster_embeddings[c]
                for i, c in enumerate(order)
                if c in cluster_embeddings
            }
            return groups, embeddings
        except Exception as e:
            log.exception("diarization failed for %s; falling back to baseline split", Path(path).name)
            if recording_id is not None:
                self._diar_note[recording_id] = (
                    f"Speaker splitting couldn't run ({type(e).__name__}), so everyone else is "
                    "shown as one speaker. Check Settings → Speech models (the speaker model "
                    "downloads on first use) and Re-process to try again."
                )
            return [(single_label, _color(base_idx), lines)], {}

    def _match_speakers_to_people(self, recording_id: int) -> list[tuple[int, int]]:
        """Auto-link this recording's speakers to known People by voice fingerprint
        (see app.voiceprints). Only links to People with an enrolled voiceprint —
        it never creates People, so the directory stays clean until the user renames
        a speaker. Best-effort: a failure must not fail the recording."""
        try:
            with Session(engine) as s:
                return match_speakers(s, recording_id)
        except Exception:
            log.exception("voice matching failed for recording %d", recording_id)
            return []

    def _mark_failed(self, recording_id: int, message: str) -> None:
        with Session(engine) as s:
            rec = s.get(Recording, recording_id)
            if rec is not None:
                rec.status = "failed"
                rec.error = message
                s.add(rec)
                s.commit()
