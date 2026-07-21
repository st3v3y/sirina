"""Local recorder: captures mic (and optional system) audio to WAV files on disk.

Runs NO inference — during a recording the only work is downmixing to mono and
writing 16-bit PCM. A separate processing job (later change) transcribes the
finished files.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import threading
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import sounddevice as sd
from sqlmodel import Session

from ..audio import system_capture
from ..audio.local import find_device
from ..audio.power import SleepBlocker
from ..audio.trim import detect_trim, trim_wav_window
from ..config import settings
from ..db import engine
from ..models import Recording

log = logging.getLogger(__name__)

CAPTURE_SR = 48_000  # capture both tracks at a common rate so they mix cleanly

# Liveness watchdog: a track that writes no data for STALL_SECONDS while recording is
# active is considered stalled. Detection keys on data *progress*, not audio level, so a
# silent-but-live source (frames still flowing) is never falsely flagged.
WATCHDOG_INTERVAL = 2.0  # seconds between liveness checks
STALL_SECONDS = 5.0  # no data for this long => stalled

# System-audio sidecar restart policy (bounded, with backoff) so a permanently
# unavailable source — e.g. revoked Screen Recording permission — can't respawn forever.
MAX_SIDECAR_RESTARTS = 5
RESTART_BASE_BACKOFF = 0.5  # seconds; doubles each attempt
RESTART_MAX_BACKOFF = 8.0

# A source track ending shorter than the recording by more than this leaves a warning.
SHORT_TRACK_ABS_S = 2.0
SHORT_TRACK_FRACTION = 0.01

# Mixing: the mic is an acoustic signal (often 20-30 dB below digital full-scale)
# while system audio is captured at its digital source level, so a naive 1:1 sum
# buries the mic under the system track. Balance each track to a target peak before
# summing, leaving headroom for the sum, and cap the boost so a near-silent track's
# noise floor isn't amplified to full scale.
MIX_TARGET_PEAK = 0.5  # per-track target peak as a fraction of int16 full-scale
MIX_MAX_GAIN = 8.0  # cap boost (~+18 dB) so quiet-track noise isn't blown up
MIX_SILENCE_PEAK = 64  # int16 peak at/below this counts as silent (left untouched)


def _recordings_dir() -> Path:
    base = settings.recordings_dir
    base.mkdir(parents=True, exist_ok=True)
    return base


class _Track:
    """One input device -> mono 16-bit PCM WAV writer, with a running input level."""

    def __init__(self, name: str, device: int | None, path: Path) -> None:
        self.name = name
        self.device = device
        self.path = path
        self.level = 0.0
        self.frames = 0
        self.restarts = 0  # PortAudio tracks don't auto-restart; kept for a uniform interface
        self.health = "healthy"  # healthy | stalled | stopped
        self.last_progress = time.monotonic()
        self._wav: wave.Wave_write | None = None
        self._stream: sd.InputStream | None = None

    def on_stall(self) -> None:
        """Called by the watchdog when this track stops producing data. PortAudio input
        rarely recovers on its own; we just surface the state (no restart here)."""

    def _note_progress(self) -> None:
        self.last_progress = time.monotonic()
        if self.health == "stalled":
            self.health = "healthy"
            log.info("track '%s' recovered", self.name)

    def start(self) -> None:
        info = (
            sd.query_devices(self.device, kind="input")
            if self.device is not None
            else sd.query_devices(kind="input")
        )
        channels = max(1, min(2, int(info["max_input_channels"])))

        wav = wave.open(str(self.path), "wb")
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(CAPTURE_SR)
        self._wav = wav

        def callback(indata: np.ndarray, frames: int, time_info, status) -> None:  # PortAudio thread
            if status:
                log.debug("portaudio status (%s): %s", self.name, status)
            try:
                if indata.ndim == 2 and indata.shape[1] > 1:
                    mono = indata.mean(axis=1)
                else:
                    mono = indata[:, 0] if indata.ndim == 2 else indata
                self.level = float(np.abs(mono).max())
                pcm16 = np.clip(mono * 32767.0, -32768, 32767).astype(np.int16)
                if self._wav is not None:
                    self._wav.writeframes(pcm16.tobytes())
                    self.frames += pcm16.size
                    self._note_progress()
            except Exception:
                log.exception("track %s write failed", self.name)

        self._stream = sd.InputStream(
            device=self.device,
            samplerate=CAPTURE_SR,
            channels=channels,
            dtype="float32",
            blocksize=CAPTURE_SR // 50,  # ~20 ms
            callback=callback,
        )
        self._stream.start()
        log.info("track '%s' capturing %s -> %s", self.name, info["name"], self.path.name)

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                log.exception("track %s stream close failed", self.name)
            self._stream = None
        if self._wav is not None:
            try:
                self._wav.close()
            except Exception:
                log.exception("track %s wav close failed", self.name)
            self._wav = None


class _SidecarTrack:
    """System-audio track fed by the native ScreenCaptureKit sidecar, which emits
    48 kHz mono s16le PCM on stdout — written straight to the WAV. Same interface as
    `_Track` (name/path/level/start/stop) so the recorder treats them alike."""

    def __init__(self, name: str, path: Path) -> None:
        self.name = name
        self.path = path
        self.level = 0.0
        self.frames = 0
        self.restarts = 0
        self.health = "healthy"  # healthy | stalled | stopped
        self.last_progress = time.monotonic()
        self._wav: wave.Wave_write | None = None
        self._proc: subprocess.Popen | None = None
        self._proc_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        wav = wave.open(str(self.path), "wb")
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(CAPTURE_SR)
        self._wav = wav
        self._spawn()
        self._thread = threading.Thread(target=self._pump, name=f"sidecar-{self.name}", daemon=True)
        self._thread.start()
        log.info("track '%s' capturing native system audio -> %s", self.name, self.path.name)

    def _spawn(self) -> None:
        """(Re)start the sidecar process and a stderr drain for it."""
        with self._proc_lock:
            self._proc = system_capture.spawn()
            proc = self._proc
        # Surface the sidecar's stderr (capture status / stop errors) to the log.
        threading.Thread(
            target=self._drain_stderr, args=(proc,), name=f"sidecar-{self.name}-err", daemon=True
        ).start()

    def on_stall(self) -> None:
        """Watchdog hook: the sidecar is alive but has gone quiet (e.g. a stop the delegate
        didn't surface). Terminate it so the blocked read returns and `_pump` can restart."""
        with self._proc_lock:
            proc = self._proc
        if proc is not None and proc.poll() is None:
            log.warning("system-audio sidecar stalled; terminating to force a restart")
            try:
                proc.terminate()
            except Exception:
                log.debug("stalled sidecar terminate failed", exc_info=True)

    def _drain_stderr(self, proc: subprocess.Popen) -> None:
        if proc.stderr is None:
            return
        for raw in iter(proc.stderr.readline, b""):
            line = raw.decode(errors="replace").strip()
            if line:
                log.info("system-audio sidecar: %s", line)

    def _restart(self) -> bool:
        """Re-spawn the sidecar to continue the same WAV, with bounded backoff. Returns
        False (giving up, track marked stopped) once the restart cap is reached."""
        if self.restarts >= MAX_SIDECAR_RESTARTS:
            self.health = "stopped"
            log.warning(
                "system-audio sidecar gave up after %d restarts; system track ends here",
                self.restarts,
            )
            return False
        self.restarts += 1
        backoff = min(RESTART_MAX_BACKOFF, RESTART_BASE_BACKOFF * (2 ** (self.restarts - 1)))
        log.warning(
            "system-audio sidecar stopped; restarting (#%d) in %.1fs", self.restarts, backoff
        )
        with self._proc_lock:
            old = self._proc
            self._proc = None
        if old is not None:
            try:
                old.kill()
            except Exception:
                pass
        if self._stop.wait(backoff):  # interruptible: stop() was called during backoff
            return False
        try:
            self._spawn()
        except Exception:
            log.exception("system-audio sidecar respawn failed")
            self.health = "stopped"
            return False
        return True

    def _pump(self) -> None:
        chunk = (CAPTURE_SR // 50) * 2  # ~20 ms of mono s16le bytes
        carry = b""  # a short pipe read can split a 16-bit sample across two reads
        while not self._stop.is_set():
            with self._proc_lock:
                proc = self._proc
            if proc is None or proc.stdout is None:
                break
            try:
                data = proc.stdout.read(chunk)
            except Exception:
                data = b""
            if not data:
                # Sidecar exited or its pipe closed (stop error, permission loss, kill).
                if self._stop.is_set() or not self._restart():
                    break
                carry = b""  # new process, new byte stream — a stale half-sample is garbage
                continue  # restarted; keep appending to the same WAV (gap = recovery time)
            data = carry + data
            usable = len(data) - (len(data) % 2)
            carry = data[usable:]
            data = data[:usable]
            if not data:
                continue
            try:
                arr = np.frombuffer(data, dtype=np.int16)
                if arr.size:
                    self.level = float(np.abs(arr).max()) / 32768.0
                if self._wav is not None:
                    self._wav.writeframes(data)
                    self.frames += arr.size
                    self.last_progress = time.monotonic()
                    if self.health == "stalled":
                        self.health = "healthy"
                        log.info("track '%s' recovered", self.name)
            except Exception:
                log.exception("sidecar pump failed for %s", self.name)
                break

    def stop(self) -> None:
        self._stop.set()
        with self._proc_lock:
            proc = self._proc
            self._proc = None
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        if self._wav is not None:
            try:
                self._wav.close()
            except Exception:
                log.exception("sidecar %s wav close failed", self.name)
            self._wav = None


class _Active:
    def __init__(self, recording_id: int, dir_path: Path, started_monotonic: float) -> None:
        self.recording_id = recording_id
        self.dir = dir_path
        self.started_monotonic = started_monotonic
        self.tracks: list[_Track | _SidecarTrack] = []
        self.sleep_blocker = SleepBlocker()
        self._watch_stop = threading.Event()
        self._watch_thread: threading.Thread | None = None

    def begin_monitoring(self) -> None:
        """Start the liveness watchdog and prevent idle sleep for this recording."""
        self.sleep_blocker.acquire()
        self._watch_thread = threading.Thread(
            target=self._watch, name=f"watchdog-{self.recording_id}", daemon=True
        )
        self._watch_thread.start()

    def _watch(self) -> None:
        # Each track updates `last_progress` when it writes data; a track that hasn't
        # advanced for STALL_SECONDS is stalled. Keys on data flow, not level, so a
        # silent-but-live source stays healthy.
        while not self._watch_stop.wait(WATCHDOG_INTERVAL):
            now = time.monotonic()
            for t in self.tracks:
                if t.health in ("stalled", "stopped"):
                    continue
                if now - t.last_progress > STALL_SECONDS:
                    t.health = "stalled"
                    log.warning(
                        "track '%s' stalled: no audio for %.1fs", t.name, now - t.last_progress
                    )
                    try:
                        t.on_stall()
                    except Exception:
                        log.exception("on_stall failed for track %s", t.name)

    def end_monitoring(self) -> None:
        self._watch_stop.set()
        if self._watch_thread is not None:
            self._watch_thread.join(timeout=2)
            self._watch_thread = None
        self.sleep_blocker.release()


class Recorder:
    """Owns at most one active recording. State machine: idle -> recording -> finalizing -> idle."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active: _Active | None = None

    def is_recording(self) -> bool:
        return self._active is not None

    def active_info(self) -> dict | None:
        a = self._active
        if a is None:
            return None
        levels = {t.name: t.level for t in a.tracks}
        by_name = {t.name: t for t in a.tracks}
        sys_track = by_name.get("system")
        mic_track = by_name.get("mic")
        return {
            "id": a.recording_id,
            "elapsed_s": time.monotonic() - a.started_monotonic,
            "level": max(levels.values(), default=0.0),
            "mic_level": levels.get("mic", 0.0),
            "system_level": levels.get("system", 0.0),
            "mic_healthy": mic_track.health == "healthy" if mic_track else True,
            "system_healthy": (sys_track.health == "healthy") if sys_track else None,
            "system_restarts": sys_track.restarts if sys_track else 0,
        }

    async def start(
        self,
        device: str | int | None,
        system_device: str | int | None,
        title: str | None,
        system_source: str = "device",
    ) -> int:
        async with self._lock:
            if self._active is not None:
                raise RuntimeError(
                    f"Already recording #{self._active.recording_id}; stop it first"
                )

            mic_dev = find_device(device)

            # Create the recording row first so we have an id for the directory.
            with Session(engine) as s:
                rec = Recording(title=title, status="recording")
                s.add(rec)
                s.commit()
                s.refresh(rec)
                recording_id = rec.id
            assert recording_id is not None

            dir_path = _recordings_dir() / str(recording_id)
            dir_path.mkdir(parents=True, exist_ok=True)

            active = _Active(recording_id, dir_path, time.monotonic())
            mic = _Track("mic", mic_dev, dir_path / "mic.wav")
            active.tracks.append(mic)
            # System source: native (ScreenCaptureKit sidecar), a loopback input
            # device (e.g. BlackHole), or none.
            sys_track: _Track | _SidecarTrack | None = None
            if system_source == "native":
                sys_track = _SidecarTrack("system", dir_path / "system.wav")
                active.tracks.append(sys_track)
            elif system_source == "device" and system_device:
                sys_dev = find_device(system_device)
                if sys_dev is not None:
                    sys_track = _Track("system", sys_dev, dir_path / "system.wav")
                    active.tracks.append(sys_track)

            try:
                for t in active.tracks:
                    t.start()
                # Opening the first PortAudio stream can block ~1-2s; start the
                # clock once audio is actually flowing so elapsed/duration are accurate.
                active.started_monotonic = time.monotonic()
                for t in active.tracks:
                    t.last_progress = active.started_monotonic
                active.begin_monitoring()
            except Exception:
                active.end_monitoring()
                for t in active.tracks:
                    t.stop()
                with Session(engine) as s:
                    rec = s.get(Recording, recording_id)
                    if rec:
                        rec.status = "failed"
                        rec.error = "failed to open audio device(s)"
                        s.add(rec)
                        s.commit()
                raise

            with Session(engine) as s:
                rec = s.get(Recording, recording_id)
                assert rec is not None
                rec.mic_path = str(mic.path)
                rec.system_path = str(sys_track.path) if sys_track else None
                s.add(rec)
                s.commit()

            self._active = active
            log.info("recording %d started (tracks=%s)", recording_id, [t.name for t in active.tracks])
            return recording_id

    async def stop(self, recording_id: int | None = None) -> dict | None:
        """Stop the active recording, finalize its files, and flip it to `processing`.

        Returns a trim suggestion ({"leading_s", "trailing_s", ...}) when the take has a
        long stretch of leading/trailing silence — in that case the recording is HELD
        (pending_trim set, not yet enqueued) awaiting the user's decision. Returns None
        when there's no significant silence (the caller enqueues it for transcription).
        """
        async with self._lock:
            active = self._active
            if active is None:
                return None
            if recording_id is not None and active.recording_id != recording_id:
                return None
            self._active = None

        active.end_monitoring()
        for t in active.tracks:
            t.stop()

        duration_s = time.monotonic() - active.started_monotonic
        mic_path = active.dir / "mic.wav"
        system_path = active.dir / "system.wav"
        has_system = system_path.exists() and any(t.name == "system" for t in active.tracks)
        warning = _incompleteness_warning(active.tracks, duration_s)

        if has_system:
            audio_path = active.dir / "mixed.wav"
            try:
                _mix_wavs(mic_path, system_path, audio_path)
            except Exception:
                log.exception("mixing failed; falling back to mic track for playback")
                audio_path = mic_path
        else:
            audio_path = mic_path

        # Offer to trim a long stretch of leading/trailing silence (e.g. a recording left
        # running long after the meeting ended) before spending time transcribing dead air.
        suggestion: dict | None = None
        min_s = settings.silence_trim_min_seconds
        if min_s > 0:
            try:
                suggestion = detect_trim(
                    mic_path if mic_path.exists() else None,
                    system_path if has_system else None,
                    min_silence_s=min_s,
                )
            except Exception:
                log.exception("silence detection failed for recording %d", active.recording_id)

        with Session(engine) as s:
            rec = s.get(Recording, recording_id or active.recording_id)
            if rec is None:
                return None
            rec.ended_at = datetime.now(timezone.utc)
            rec.duration_s = duration_s
            rec.audio_path = str(audio_path)
            rec.system_path = str(system_path) if has_system else None
            rec.warning = warning
            rec.status = "processing"
            # A trim suggestion HOLDS the recording (not enqueued) until the user decides;
            # the API layer only enqueues when this returns None.
            rec.pending_trim = json.dumps(suggestion) if suggestion else None
            s.add(rec)
            s.commit()
        log.info(
            "recording %d stopped (%.1fs)%s",
            active.recording_id, duration_s,
            " -> awaiting trim decision" if suggestion else " -> processing",
        )
        return suggestion

    def active_id(self) -> int | None:
        """The id of the currently-active recording, or None when idle."""
        return self._active.recording_id if self._active else None


def _wav_duration_s(path: Path) -> float:
    """Duration of a mono PCM WAV from its frame count, or 0.0 if unreadable/empty."""
    try:
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate() or CAPTURE_SR)
    except Exception:
        return 0.0


def recover_orphaned(recording_id: int) -> bool:
    """Finalize a recording left stuck in `recording` by a crash/force-quit before `stop()`
    ever ran: mix the on-disk tracks, set duration/paths/ended_at, and flip it to
    `processing` so it can be (re)transcribed. Returns True if any audio was recovered,
    False if the recording captured nothing to process.

    This is the recovery path behind Re-process for a recording whose files exist on disk
    but were never finalized (no mixed track, no duration). It mirrors the tail of `stop()`.
    """
    rec_dir = settings.recordings_dir / str(recording_id)
    mic_path = rec_dir / "mic.wav"
    system_path = rec_dir / "system.wav"
    has_mic = _wav_duration_s(mic_path) > 0
    has_system = _wav_duration_s(system_path) > 0
    if not has_mic and not has_system:
        return False
    duration_s = max(_wav_duration_s(mic_path), _wav_duration_s(system_path))

    if has_mic and has_system:
        audio_path = rec_dir / "mixed.wav"
        try:
            _mix_wavs(mic_path, system_path, audio_path)
        except Exception:
            log.exception("recover %d: mixing failed; falling back to mic track", recording_id)
            audio_path = mic_path
    else:
        audio_path = mic_path if has_mic else system_path

    with Session(engine) as s:
        rec = s.get(Recording, recording_id)
        if rec is None:
            return False
        rec.mic_path = str(mic_path) if has_mic else None
        rec.system_path = str(system_path) if has_system else None
        rec.audio_path = str(audio_path)
        rec.duration_s = duration_s
        rec.ended_at = rec.ended_at or datetime.now(timezone.utc)
        rec.status = "processing"
        rec.error = None
        s.add(rec)
        s.commit()
    log.info("recovered orphaned recording %d (%.1fs) -> processing", recording_id, duration_s)
    return True


def apply_trim(recording_id: int, start_s: float, end_s: float) -> float:
    """Trim every on-disk track of a recording to the absolute window [start_s, end_s],
    re-mix, and update the stored duration. Clears `pending_trim`. Returns the new duration.

    Tracks share a common start (t=0) so the same window applies to all; trim_wav_window
    clamps to each file's own length. The trimmed files replace the originals in place."""
    rec_dir = settings.recordings_dir / str(recording_id)
    mic_path = rec_dir / "mic.wav"
    system_path = rec_dir / "system.wav"

    def _trim_in_place(path: Path) -> bool:
        if not path.exists():
            return False
        tmp = path.with_suffix(".trim.wav")
        trim_wav_window(path, tmp, start_s, end_s)
        os.replace(tmp, path)
        return True

    has_mic = _trim_in_place(mic_path)
    has_system = _trim_in_place(system_path)

    if has_mic and has_system:
        audio_path = rec_dir / "mixed.wav"
        try:
            _mix_wavs(mic_path, system_path, audio_path)
        except Exception:
            log.exception("trim %d: re-mix failed; falling back to mic track", recording_id)
            audio_path = mic_path
    else:
        audio_path = mic_path if has_mic else system_path

    new_duration = max(0.0, end_s - start_s)
    with Session(engine) as s:
        rec = s.get(Recording, recording_id)
        if rec is not None:
            rec.duration_s = new_duration
            rec.audio_path = str(audio_path)
            rec.mic_path = str(mic_path) if has_mic else None
            rec.system_path = str(system_path) if has_system else None
            rec.pending_trim = None
            s.add(rec)
            s.commit()
    log.info("trimmed recording %d to %.1fs (window %.1f–%.1f)", recording_id, new_duration, start_s, end_s)
    return new_duration


def _fmt_minutes(seconds: float) -> str:
    return f"{seconds / 60:.1f} min"


def _incompleteness_warning(
    tracks: list["_Track | _SidecarTrack"], duration_s: float
) -> str | None:
    """If a source track ended materially shorter than the recording (so the mix had to
    pad it with silence), describe the shortfall so the partial track isn't presented as
    complete. Returns None when every source spans the full duration within tolerance."""
    tol = max(SHORT_TRACK_ABS_S, SHORT_TRACK_FRACTION * duration_s)
    for t in tracks:
        track_s = t.frames / CAPTURE_SR
        if duration_s - track_s > tol:
            label = "System audio" if t.name == "system" else f"{t.name.capitalize()} audio"
            return (
                f"{label} captured only {_fmt_minutes(track_s)} of {_fmt_minutes(duration_s)} — "
                "the rest is missing (the source stopped delivering audio mid-recording)."
            )
    return None


# One minute of 48 kHz mono int16 per block (~5.5 MB): bounded memory no matter how
# long the recording is. The old whole-file mix needed gigabytes for multi-hour takes.
_MIX_BLOCK_FRAMES = CAPTURE_SR * 60


def _wav_peak(path: Path) -> float:
    """Peak |amplitude| of a mono 16-bit WAV, read block-wise."""
    peak = 0
    with wave.open(str(path), "rb") as wf:
        while True:
            raw = wf.readframes(_MIX_BLOCK_FRAMES)
            if not raw:
                break
            arr = np.frombuffer(raw, dtype=np.int16)
            if arr.size:
                peak = max(peak, int(np.abs(arr).max()))
    return float(peak)


def _balance_gain(peak: float) -> float:
    """Gain bringing a track's peak up to MIX_TARGET_PEAK, capped at MIX_MAX_GAIN.
    A silent track is left untouched so its noise floor isn't amplified."""
    if peak <= MIX_SILENCE_PEAK:
        return 1.0
    return min(MIX_MAX_GAIN, (MIX_TARGET_PEAK * 32767.0) / peak)


def _mix_wavs(a: Path, b: Path, out: Path) -> None:
    """Mix two mono 16-bit WAVs (same rate) into one, block-wise (bounded memory on
    multi-hour recordings). Each track is level-balanced to comparable loudness before
    summing so the (quieter) mic isn't buried under full-scale system audio; the sum is
    hard-clipped to int16 as a final safety net. The shorter track is padded with
    silence to the longer one's length."""
    gain_a = _balance_gain(_wav_peak(a))
    gain_b = _balance_gain(_wav_peak(b))
    with wave.open(str(a), "rb") as wa, wave.open(str(b), "rb") as wb, wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(CAPTURE_SR)
        while True:
            raw_a = wa.readframes(_MIX_BLOCK_FRAMES)
            raw_b = wb.readframes(_MIX_BLOCK_FRAMES)
            if not raw_a and not raw_b:
                break
            xa = np.frombuffer(raw_a, dtype=np.int16).astype(np.float32)
            xb = np.frombuffer(raw_b, dtype=np.int16).astype(np.float32)
            n = max(xa.size, xb.size)
            if xa.size < n:
                xa = np.pad(xa, (0, n - xa.size))
            if xb.size < n:
                xb = np.pad(xb, (0, n - xb.size))
            mixed = np.clip(xa * gain_a + xb * gain_b, -32768, 32767).astype(np.int16)
            wf.writeframes(mixed.tobytes())
