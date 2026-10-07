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
from typing import TYPE_CHECKING

import numpy as np
import sounddevice as sd
from sqlmodel import Session

from ..audio import system_capture
from ..audio.local import find_device, refresh_devices
from ..audio.power import power_guard
from ..audio.trim import detect_trim, trim_wav_window
from ..config import settings
from ..db import engine
from ..models import Recording

if TYPE_CHECKING:
    from .captions import CaptionStream
    from .live import LiveFinalizer

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

# PortAudio (mic / loopback-device) recovery: retry reopening until the recording stops,
# backing off to this cap. A device that stalls again this soon after being reopened is
# treated as unreliable and the mic switches to the default input instead.
PA_REOPEN_BASE_BACKOFF = 1.0
PA_REOPEN_MAX_BACKOFF = 10.0
PA_REPEAT_STALL_S = 60.0
# Failed passes (~35 s of backoff) before a track that can't be reopened is given up on —
# only when retrying keeps disturbing another healthy PortAudio track.
PA_MAX_FAILED_PASSES = 6

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


def _fmt_clock(seconds: float) -> str:
    """Recording-relative time as m:ss (or h:mm:ss)."""
    total = max(0, int(seconds))
    h, rem = divmod(total, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _write_silence(wav: wave.Wave_write, frames: int, tap=None) -> None:
    """Append `frames` of digital silence, in bounded blocks (an outage can be minutes).
    `tap` (live captions) gets the same bytes so caption times stay on the WAV timeline."""
    block = np.zeros(CAPTURE_SR * 10, dtype=np.int16).tobytes()
    while frames > 0:
        n = min(frames, CAPTURE_SR * 10)
        wav.writeframes(block[: n * 2])
        if tap is not None:
            tap(block[: n * 2])
        frames -= n


def _gap_frames(anchor: float, frames: int, pending: int = 0) -> int:
    """Frames of silence needed so a track that lost audio realigns with the wall clock:
    the track should hold (now - anchor) seconds of audio, `pending` of which are about
    to be written. Tracks share a common t=0, so a gap that isn't filled shifts every
    later line of this track earlier than the other track's."""
    return max(0, int((time.monotonic() - anchor) * CAPTURE_SR) - frames - pending)


class _Track:
    """One input device -> mono 16-bit PCM WAV writer, with a running input level.

    PortAudio input doesn't recover on its own when its device drops out (a Bluetooth
    headset disconnecting, an iPhone Continuity mic going away): callbacks simply stop.
    The recording's watchdog then calls `_Active.recover_portaudio`, which reopens the
    stream via `reopen()` — padding the outage with silence so the timeline stays aligned."""

    def __init__(self, name: str, device: int | None, path: Path) -> None:
        self.name = name
        self.device = device
        self.device_name: str | None = None
        self.path = path
        self.level = 0.0
        self.frames = 0
        self.restarts = 0  # successful reopens after a stall
        self.health = "healthy"  # healthy | stalled | stopped
        self.last_progress = time.monotonic()
        self.anchor = time.monotonic()  # wall-clock time of this track's frame 0
        self.tap = None  # optional fn(bytes): every PCM block written (live captions)
        self.events: list[str] = []  # user-facing notes (dropouts), surfaced on the recording
        self.last_reopen_at: float | None = None
        self.failed_reopens = 0  # consecutive failed recovery passes
        self._wav: wave.Wave_write | None = None
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()  # serializes stream swaps against stop()
        self._closed = False

    def on_stall(self) -> None:
        """Watchdog hook. Recovery needs every PortAudio track (re-enumerating devices
        tears down all streams), so `_Active` drives it for any stalled `_Track`."""

    def _note_progress(self) -> None:
        self.last_progress = time.monotonic()
        if self.health == "stalled":
            self.health = "healthy"
            log.info("track '%s' recovered", self.name)

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:  # PortAudio thread
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
                data = pcm16.tobytes()
                self._wav.writeframes(data)
                self.frames += pcm16.size
                self._note_progress()
                if self.tap is not None:
                    self.tap(data)
        except Exception:
            log.exception("track %s write failed", self.name)

    def _make_stream(self, device: int | None) -> tuple[sd.InputStream, str]:
        info = (
            sd.query_devices(device, kind="input")
            if device is not None
            else sd.query_devices(kind="input")
        )
        channels = max(1, min(2, int(info["max_input_channels"])))
        stream = sd.InputStream(
            device=device,
            samplerate=CAPTURE_SR,
            channels=channels,
            dtype="float32",
            blocksize=CAPTURE_SR // 50,  # ~20 ms
            callback=self._callback,
        )
        return stream, str(info["name"])

    def start(self) -> None:
        wav = wave.open(str(self.path), "wb")
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(CAPTURE_SR)
        self._wav = wav
        stream, name = self._make_stream(self.device)
        stream.start()
        self.anchor = time.monotonic()
        self._stream = stream
        self.device_name = name
        log.info("track '%s' capturing %s -> %s", self.name, name, self.path.name)

    def close_stream(self) -> None:
        """Tear down the (possibly dead) stream, keeping the WAV open for a reopen."""
        with self._lock:
            stream, self._stream = self._stream, None
        if stream is not None:
            for op in (stream.abort, stream.close):
                try:
                    op()
                except Exception:
                    log.debug("track %s stream %s failed", self.name, op.__name__, exc_info=True)

    def reopen(self, *, allow_fallback: bool, avoid_current: bool = False) -> str:
        """Reopen capture after a dropout and return the device name now in use. Must run
        after PortAudio was re-initialized (device indices change). Looks the original
        device up by name; if it's gone (or `avoid_current`, because it keeps stalling)
        and `allow_fallback`, uses the system default input instead. The outage is padded
        with silence before the new stream starts. Raises when nothing could be opened."""
        with self._lock:
            if self._closed or self._wav is None:
                raise RuntimeError("track closed")
            device: int | None = None
            found = False
            if self.device_name and not avoid_current:
                for i, d in enumerate(sd.query_devices()):
                    if int(d.get("max_input_channels", 0) or 0) > 0 and d["name"] == self.device_name:
                        device, found = i, True
                        break
            if not found and not allow_fallback:
                raise RuntimeError(f"input device {self.device_name!r} is not available")
            if not found and avoid_current:
                # The default input is often the very device that keeps stalling (macOS
                # makes a connected headset the default) — pick another input then.
                default = sd.query_devices(kind="input")
                if default["name"] == self.device_name:
                    device = next(
                        (
                            i for i, d in enumerate(sd.query_devices())
                            if int(d.get("max_input_channels", 0) or 0) > 0
                            and d["name"] != self.device_name
                        ),
                        None,
                    )
                    if device is None:
                        raise RuntimeError(f"no input other than {self.device_name!r}")
            stream, name = self._make_stream(device)
            pad = _gap_frames(self.anchor, self.frames)
            if pad:
                _write_silence(self._wav, pad, self.tap)
                self.frames += pad
            stream.start()
            self._stream = stream
            self.device = device
            self.device_name = name
            self.restarts += 1
            self.last_reopen_at = time.monotonic()
            return name

    def stop(self) -> None:
        with self._lock:
            self._closed = True
        self.close_stream()
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
        self.anchor = time.monotonic()  # wall-clock time of this track's frame 0
        self.tap = None  # optional fn(bytes): every PCM block written (live captions)
        self.events: list[str] = []  # user-facing notes (dropouts), surfaced on the recording
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
        self.anchor = time.monotonic()
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
        lost_at: float | None = None  # last audio before a restart; the gap is filled on resume
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
                if lost_at is None:
                    lost_at = self.last_progress
                if self._stop.is_set() or not self._restart():
                    break
                carry = b""  # new process, new byte stream — a stale half-sample is garbage
                continue  # restarted; keep appending to the same WAV (gap filled on resume)
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
                    if lost_at is not None:
                        # First audio after a restart: pad the outage with silence so later
                        # system lines stay aligned with the mic track.
                        pad = _gap_frames(self.anchor, self.frames, pending=arr.size)
                        if pad:
                            _write_silence(self._wav, pad, self.tap)
                            self.frames += pad
                        self.events.append(
                            f"System audio dropped out at {_fmt_clock(lost_at - self.anchor)} "
                            f"for {time.monotonic() - lost_at:.0f} s (filled with silence)."
                        )
                        lost_at = None
                    self._wav.writeframes(data)
                    self.frames += arr.size
                    self.last_progress = time.monotonic()
                    if self.tap is not None:
                        self.tap(data)
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
        self._watch_stop = threading.Event()
        self._watch_thread: threading.Thread | None = None
        self._recover_thread: threading.Thread | None = None
        self._recover_lock = threading.Lock()
        # track -> (last audio before the dropout, device it was on). Reported once the
        # track is delivering again, so a reopen that needs several passes is one note.
        self._outages: dict[_Track, tuple[float, str | None]] = {}
        self._outage_lock = threading.Lock()

    def begin_monitoring(self) -> None:
        """Start the liveness watchdog and prevent idle sleep for this recording."""
        power_guard.hold(("recording", self.recording_id))
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
            # Checked every tick, not only on a fresh stall: a track that stalls while a
            # recovery pass is finishing up would otherwise never be picked up again.
            if any(isinstance(t, _Track) and t.health == "stalled" for t in self.tracks):
                self._start_recovery()

    def _start_recovery(self) -> None:
        with self._recover_lock:
            if self._recover_thread is not None and self._recover_thread.is_alive():
                return  # the running pass picks up every stalled PortAudio track
            self._recover_thread = threading.Thread(
                target=self.recover_portaudio, name=f"recover-{self.recording_id}", daemon=True
            )
            self._recover_thread.start()

    def recover_portaudio(self) -> None:
        """Bring stalled PortAudio tracks back, retrying with backoff until the recording
        stops. A dropped device (Bluetooth headset, iPhone mic) may come back under a new
        index, so PortAudio is re-initialized to see it — which tears down EVERY PortAudio
        stream, so healthy PortAudio tracks are reopened too (their few ms are gap-filled).
        The mic falls back to the default input when its device is gone: capturing the
        user's voice on another mic beats losing the rest of the meeting."""
        backoff = PA_REOPEN_BASE_BACKOFF
        outages = self._outages
        while not self._watch_stop.is_set():
            pa_tracks = [t for t in self.tracks if isinstance(t, _Track)]
            self._flush_outages()
            stalled = [t for t in pa_tracks if t.health == "stalled"]
            if not stalled:
                return
            with self._outage_lock:
                for t in stalled:
                    outages.setdefault(t, (t.last_progress, t.device_name))
            try:
                for t in pa_tracks:
                    t.close_stream()
                refresh_devices()
                for t in pa_tracks:
                    if t.health == "stalled":
                        continue
                    try:
                        t.reopen(allow_fallback=False)
                    except Exception:
                        # It will stall in turn and be retried by the next pass.
                        log.warning("couldn't reopen healthy track '%s'", t.name, exc_info=True)
                failed = False
                for t in stalled:
                    # Reopened before and stalled again without delivering (or soon after):
                    # that device is unreliable — the mic moves to another input.
                    repeat = t.last_reopen_at is not None and (
                        t.last_progress <= t.last_reopen_at
                        or t.last_progress - t.last_reopen_at < PA_REPEAT_STALL_S
                    )
                    is_mic = t.name == "mic"
                    try:
                        name = t.reopen(allow_fallback=is_mic, avoid_current=repeat and is_mic)
                    except Exception:
                        failed = True
                        t.failed_reopens += 1
                        log.warning("couldn't reopen track '%s'", t.name, exc_info=True)
                        # Every pass tears down the other PortAudio tracks too. Once this one
                        # looks permanently gone (e.g. a removed loopback device), stop
                        # retrying rather than chopping a healthy mic every few seconds.
                        others_live = any(o is not t and o.health == "healthy" for o in pa_tracks)
                        if others_live and t.failed_reopens >= PA_MAX_FAILED_PASSES:
                            t.health = "stopped"
                            log.warning("giving up on track '%s'; it ends here", t.name)
                        continue
                    t.failed_reopens = 0
                    log.warning(
                        "track '%s' reopened on %s after %.1fs without audio",
                        t.name, name, time.monotonic() - outages[t][0],
                    )
            except Exception:
                failed = True
                log.warning("re-initializing audio input failed", exc_info=True)
            if failed:
                log.info("retrying stalled audio input in %.0fs", backoff)
                if self._watch_stop.wait(backoff):
                    return
                backoff = min(PA_REOPEN_MAX_BACKOFF, backoff * 2)
            else:
                backoff = PA_REOPEN_BASE_BACKOFF
                # Give the reopened streams a moment to deliver before checking again.
                if self._watch_stop.wait(STALL_SECONDS):
                    return

    def _flush_outages(self) -> None:
        """Turn dropouts of tracks that are delivering again into recording notes. Locked:
        stop() flushes too, and may run while a slow reopen is still in progress."""
        with self._outage_lock:
            for t, (lost_at, old) in list(self._outages.items()):
                if t.health == "healthy":
                    del self._outages[t]
                    self._note_outage(t, lost_at, old)

    @staticmethod
    def _note_outage(t: "_Track", lost_at: float, old: str | None) -> None:
        resumed = t.last_reopen_at or time.monotonic()
        switched = f", continued on {t.device_name}" if t.device_name != old else ""
        t.events.append(
            f"{t.name.capitalize()} ({old}) dropped out at {_fmt_clock(lost_at - t.anchor)} "
            f"for {max(0.0, resumed - lost_at):.0f} s{switched}; the gap is silent."
        )

    def end_monitoring(self) -> None:
        self._watch_stop.set()
        if self._watch_thread is not None:
            self._watch_thread.join(timeout=2)
            self._watch_thread = None
        if self._recover_thread is not None:
            self._recover_thread.join(timeout=5)
            self._recover_thread = None
        self._flush_outages()  # a reconnect that landed just before stop is still reported
        # The processing job takes its own hold when enqueued, so idle sleep stays blocked
        # until transcription finishes, not just until the recording stops.
        power_guard.release(("recording", self.recording_id))


def _store_caption_drafts(recording_id: int, lines: dict, has_system: bool, mic_path: str,
                          system_path: str | None) -> None:
    """Persist settled captions as draft lines after the part that's already final."""
    from ..processing.job import _color
    from ..processing.windows import insert_drafts, tracks_for
    from ..transcribe.whisper import TLine

    tracks = tracks_for(mic_path, system_path, mic_path, _color) if has_system else tracks_for(None, None, mic_path, _color)
    by_name = {"mic": tracks[0], "system": tracks[1]} if has_system else {"mic": tracks[0]}
    with Session(engine) as s:
        rec = s.get(Recording, recording_id)
        after = float(rec.final_until_s or 0.0) if rec else 0.0
    pairs = [
        (by_name[name], [TLine(a, b, t) for (a, b, t) in caps])
        for name, caps in lines.items() if name in by_name and caps
    ]
    insert_drafts(engine, recording_id, pairs, after)


def captions_available() -> bool:
    """Live captions need the speech helper with on-device speech (macOS 26+)."""
    from ..transcribe.speech_helper import helper_path, probe

    return bool(helper_path() and probe().get("apple_speech"))


def live_transcription_available() -> bool:
    """Transcription during recording runs only on WhisperKit (light enough for a call)."""
    from ..runtime import runtime

    return getattr(runtime.whisper, "name", "") == "whisperkit"


class Recorder:
    """Owns at most one active recording. State machine: idle -> recording -> finalizing -> idle."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active: _Active | None = None
        # Opt-in speech work for the active recording (see live.py / captions.py).
        self._captions: dict[str, "CaptionStream"] = {}
        self._caption_lines: dict[str, list[tuple[float, float, str]]] = {}  # from stopped streams
        self._live: "LiveFinalizer | None" = None

    def is_recording(self) -> bool:
        return self._active is not None

    def live_finalizing(self) -> bool:
        return self._live is not None and self._live.enabled

    # ---------------------------------------------------------- live captions

    def _start_captions(self, active: "_Active") -> None:
        from ..transcribe.speech_helper import helper_path
        from .captions import CaptionStream

        path = helper_path()
        if not path:
            return
        for t in active.tracks:
            if t.name in self._captions:
                continue
            try:
                cs = CaptionStream(
                    path,
                    offset_s=t.frames / CAPTURE_SR,  # started mid-recording → recording time
                    language=settings.whisper_language or None,
                    prompt=settings.whisper_initial_prompt or None,
                    sample_rate=CAPTURE_SR,
                )
            except Exception:
                log.exception("could not start captions for track %s", t.name)
                continue
            self._captions[t.name] = cs
            t.tap = cs.feed

    def _stop_captions(self, active: "_Active") -> None:
        for t in active.tracks:
            t.tap = None
        for name, cs in list(self._captions.items()):
            try:
                self._caption_lines.setdefault(name, []).extend(cs.stop())
            except Exception:
                log.exception("stopping captions for %s failed", name)
        self._captions.clear()

    # ---------------------------------------------------------- transcription during recording

    def _start_live(self, active: "_Active") -> None:
        from ..processing.job import _color
        from ..processing.windows import tracks_for
        from ..runtime import runtime
        from .live import LiveFinalizer

        if self._live is not None:
            self._live.enabled = True
            return
        names = {t.name: t for t in active.tracks}
        mic, sysw = names.get("mic"), names.get("system")
        tracks = tracks_for(
            str(mic.path) if mic else None, str(sysw.path) if sysw else None,
            str((mic or sysw).path) if (mic or sysw) else None, _color,
        )

        def recorded_s() -> float:
            return min((t.frames for t in active.tracks), default=0) / CAPTURE_SR

        engine_ = runtime.whisper

        async def transcribe_window(path, start_s, end_s, *, language=None):
            # The startup load may still be running (or need the one-time download).
            if not engine_.is_loaded():
                await engine_.load()
            return await engine_.transcribe_window(path, start_s, end_s, language=language)

        diarize = None
        proc = runtime.processor
        if settings.diarization_timing == "during_recording" and proc is not None:
            two = sysw is not None
            mic_path = str(mic.path) if mic else None
            sys_path = str(sysw.path) if sysw else None

            async def diarize(until_s: float) -> None:
                await proc.split_speakers_live(active.recording_id, two, mic_path, sys_path)

        self._live = LiveFinalizer(active.recording_id, tracks, recorded_s, transcribe_window, diarize=diarize)
        self._live.start()

    async def set_options(self, *, live_transcribe: bool | None = None, live_captions: bool | None = None) -> dict:
        """Change the opt-in speech work of the active recording (recording screen toggles)."""
        a = self._active
        if a is None:
            raise RuntimeError("not recording")
        if live_captions is not None:
            if live_captions and captions_available():
                self._start_captions(a)
            elif not live_captions:
                self._stop_captions(a)
        if live_transcribe is not None:
            if live_transcribe and live_transcription_available():
                self._start_live(a)
            elif not live_transcribe and self._live is not None:
                self._live.enabled = False  # the window in progress may still finish
        with Session(engine) as s:
            rec = s.get(Recording, a.recording_id)
            if rec is not None:
                rec.live_captions = bool(self._captions)
                rec.live_transcribe = self.live_finalizing()
                s.add(rec)
                s.commit()
        return self.active_info() or {}

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
            "live_captions": bool(self._captions),
            "live_transcribe": self.live_finalizing(),
            "live": self._live.snapshot() if self._live is not None else None,
            "captions": {name: cs.snapshot() for name, cs in self._captions.items()},
            "captions_available": captions_available(),
            "live_transcribe_available": live_transcription_available(),
        }

    async def start(
        self,
        device: str | int | None,
        system_device: str | int | None,
        title: str | None,
        system_source: str = "device",
        live_transcribe: bool | None = None,
        live_captions: bool | None = None,
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

            # Opt-in speech work: defaults from Settings, overridable per recording.
            want_live = settings.live_transcribe_default if live_transcribe is None else live_transcribe
            want_caps = settings.live_captions_default if live_captions is None else live_captions
            self._caption_lines = {}
            if want_caps and captions_available():
                self._start_captions(active)
            if want_live and live_transcription_available():
                self._start_live(active)

            with Session(engine) as s:
                rec = s.get(Recording, recording_id)
                assert rec is not None
                rec.mic_path = str(mic.path)
                rec.system_path = str(sys_track.path) if sys_track else None
                rec.live_captions = bool(self._captions)
                rec.live_transcribe = self.live_finalizing()
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

        # No live window may commit after this point (the job redoes an in-flight one).
        live, self._live = self._live, None
        if live is not None:
            await live.stop()
        active.end_monitoring()
        for t in active.tracks:
            t.stop()
        # Captions get every sample first, then finish; their settled lines become the
        # draft for whatever isn't final yet.
        self._stop_captions(active)
        caption_lines, self._caption_lines = self._caption_lines, {}

        duration_s = time.monotonic() - active.started_monotonic
        mic_path = active.dir / "mic.wav"
        system_path = active.dir / "system.wav"
        has_system = system_path.exists() and any(t.name == "system" for t in active.tracks)
        # Dropouts that were bridged (gap filled, maybe on another mic) and any shortfall
        # that wasn't, so a partial track is never presented as complete.
        notes = [e for t in active.tracks for e in t.events]
        warning = " ".join(filter(None, [*notes, _incompleteness_warning(active.tracks, duration_s)])) or None

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
        if any(caption_lines.values()):
            try:
                _store_caption_drafts(active.recording_id, caption_lines, has_system, str(mic_path),
                                      str(system_path) if has_system else None)
            except Exception:
                log.exception("storing caption drafts failed for recording %d", active.recording_id)
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


def shift_transcript(s: Session, recording_id: int, start_s: float, end_s: float,
                     final_until_s: float | None) -> float | None:
    """Drop segments starting outside [start_s, end_s), shift the rest (and their word
    timings) by -start_s, remove speakers left without lines, and return the shifted
    `final_until_s` (None when nothing final survives)."""
    from sqlmodel import select

    from ..models import Segment, Speaker

    span = max(0.0, end_s - start_s)
    for seg in s.exec(select(Segment).where(Segment.recording_id == recording_id)).all():
        if seg.start_ts < start_s or seg.start_ts >= end_s:
            s.delete(seg)
            continue
        seg.start_ts -= start_s
        seg.end_ts = min(span, seg.end_ts - start_s)
        if seg.words:
            seg.words = json.dumps([[w[0] - start_s, w[1] - start_s, w[2]] for w in json.loads(seg.words)])
        s.add(seg)
    s.flush()
    for sp in s.exec(select(Speaker).where(Speaker.recording_id == recording_id)).all():
        if s.exec(select(Segment.id).where(Segment.speaker_id == sp.id)).first() is None:
            s.delete(sp)
    if final_until_s is None:
        return None
    shifted = min(span, final_until_s - start_s)
    return shifted if shifted > 0 else None


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
            # Lines written before the decision (live windows, caption drafts) move onto
            # the trimmed timeline, so the transcript matches the trimmed audio.
            rec.final_until_s = shift_transcript(s, recording_id, start_s, end_s, rec.final_until_s)
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
