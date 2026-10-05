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
from .compress import compress_recording, restore_wavs
from .diarize import Diarizer, diarize_lines
from .segment import resegment_lines

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
    which otherwise make MLX/Whisper hallucinate phrases on the silence."""
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
        # Non-streaming engines (MLX): estimate a fraction from elapsed time vs an
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

        await self._whisper.load()
        two_track = bool(mic_path and system_path and Path(mic_path).exists() and Path(system_path).exists())
        use_diar = self._diarizer is not None and self._diarizer.is_available()
        # Streaming engines (faster-whisper) report a real fraction via progress_cb.
        # Non-streaming engines (MLX) get a time-based estimate from audio duration
        # (×2 for two-track, since mic and system are each transcribed).
        if getattr(self._whisper, "streams_progress", True):
            self._set_progress(recording_id, "transcribing", None)
        else:
            mult = 2 if two_track else 1
            est = duration_s * settings.transcribe_rt_factor * mult if duration_s > 0 else None
            self._set_progress(recording_id, "transcribing", None, est_total=est)
        if settings.dev:
            log.debug(
                "processing recording %d: engine=%s two_track=%s diar=%s duration=%.1fs",
                recording_id, getattr(self._whisper, "name", "?"), two_track, use_diar, duration_s,
            )

        # 1) Transcribe (no diarization yet), skipping silent tracks. A silent track
        #    (e.g. a system/BlackHole capture with nothing playing) would otherwise make
        #    MLX/Whisper hallucinate captions ("Thanks for watching.") on the silence.
        #    Word timestamps are always on: segment-level times are unreliable across
        #    silence (with VAD a segment straddling removed silence maps back to a span
        #    of many minutes), and the two tracks are interleaved purely by start time —
        #    word times are what keep "who said what when" in the right order.
        mic_lines: list = []
        sys_lines: list = []
        lines: list = []
        language: str | None = None
        if two_track:
            todo = [
                name
                for name, path in (("mic", mic_path), ("system", system_path))
                if not _is_silent(path)  # type: ignore[arg-type]
            ]
            if "mic" not in todo:
                log.info("recording %d: mic track is silent — skipping", recording_id)
            if "system" not in todo:
                log.info("recording %d: system track is silent — skipping (no 'Others')", recording_id)
            log.info("transcribing recording %d (two-track; %d non-silent)", recording_id, len(todo))
            baseline = []
            for i, name in enumerate(todo):
                lo, hi = i / len(todo), (i + 1) / len(todo)
                if name == "mic":
                    mic_lines, lang = await self._whisper.transcribe_file(
                        mic_path, word_timestamps=True, progress_cb=self._progress_cb(recording_id, lo, hi)  # type: ignore[arg-type]
                    )
                    language = language or lang
                    baseline.append(("You", _color(0), mic_lines))
                else:
                    sys_lines, lang = await self._whisper.transcribe_file(
                        system_path, word_timestamps=True, progress_cb=self._progress_cb(recording_id, lo, hi)  # type: ignore[arg-type]
                    )
                    language = language or lang
                    baseline.append(("Speaker 1", _color(1), sys_lines))
        elif _is_silent(audio_path):  # type: ignore[arg-type]
            log.info("recording %d: single track is silent — no transcript", recording_id)
            baseline = []
        else:
            log.info("transcribing recording %d (single track)", recording_id)
            lines, language = await self._whisper.transcribe_file(
                audio_path, word_timestamps=True, progress_cb=self._progress_cb(recording_id, 0.0, 1.0)
            )
            baseline = [("Speaker 1", _color(0), lines)]

        # 2) Persist the baseline transcript immediately so it's visible while the
        #    (slower) diarization and summary stages still run. Row-by-row insert of a
        #    long transcript is blocking DB work — off the event loop.
        total = await asyncio.to_thread(self._write_tracks, recording_id, baseline, language)
        lines_present = total > 0
        log.info("recording %d transcribed (%d segments, lang=%s)", recording_id, total, language)

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

        diar_note = self._diar_note.pop(recording_id, None)
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
            # DiarizationResult with per-cluster embeddings.
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
                if isinstance(e, (ImportError, ModuleNotFoundError)):
                    # Don't send the user chasing tokens — the module isn't in this build.
                    self._diar_note[recording_id] = (
                        "Speaker splitting isn't included in this build of the app, so everyone "
                        "else is shown as one speaker. Rebuild with ./scripts/build-macos-app.sh "
                        "--diarization (or run from source) to enable it."
                    )
                else:
                    self._diar_note[recording_id] = (
                        f"Speaker splitting couldn't run ({type(e).__name__}), so everyone else is "
                        "shown as one speaker. Check your HuggingFace token and that you've accepted "
                        "the pyannote model terms in Settings → Speaker diarization."
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
