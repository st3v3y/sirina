"""Local recorder: captures mic (and optional system) audio to WAV files on disk.

Runs NO inference — during a recording the only work is downmixing to mono and
writing 16-bit PCM. A separate processing job (later change) transcribes the
finished files.
"""
from __future__ import annotations

import asyncio
import logging
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
from ..config import settings
from ..db import engine
from ..models import Recording

log = logging.getLogger(__name__)

CAPTURE_SR = 48_000  # capture both tracks at a common rate so they mix cleanly

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
        self._wav: wave.Wave_write | None = None
        self._stream: sd.InputStream | None = None

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
        self._wav: wave.Wave_write | None = None
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        wav = wave.open(str(self.path), "wb")
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(CAPTURE_SR)
        self._wav = wav
        self._proc = system_capture.spawn()
        self._thread = threading.Thread(target=self._pump, name=f"sidecar-{self.name}", daemon=True)
        self._thread.start()
        # Surface the sidecar's stderr (capture status / errors) to the log.
        threading.Thread(target=self._drain_stderr, name=f"sidecar-{self.name}-err", daemon=True).start()
        log.info("track '%s' capturing native system audio -> %s", self.name, self.path.name)

    def _drain_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for raw in iter(proc.stderr.readline, b""):
            line = raw.decode(errors="replace").strip()
            if line:
                log.info("system-audio sidecar: %s", line)

    def _pump(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        chunk = (CAPTURE_SR // 50) * 2  # ~20 ms of mono s16le bytes
        try:
            while not self._stop.is_set():
                data = proc.stdout.read(chunk)
                if not data:
                    break  # sidecar exited (e.g. permission lost) → leaves a silent/short track
                arr = np.frombuffer(data, dtype=np.int16)
                if arr.size:
                    self.level = float(np.abs(arr).max()) / 32768.0
                if self._wav is not None:
                    self._wav.writeframes(data)
                    self.frames += arr.size
        except Exception:
            log.exception("sidecar pump failed for %s", self.name)

    def stop(self) -> None:
        self._stop.set()
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
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
        self.tracks: list[_Track] = []


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
        return {
            "id": a.recording_id,
            "elapsed_s": time.monotonic() - a.started_monotonic,
            "level": max(levels.values(), default=0.0),
            "mic_level": levels.get("mic", 0.0),
            "system_level": levels.get("system", 0.0),
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
            except Exception:
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

    async def stop(self, recording_id: int | None = None) -> None:
        async with self._lock:
            active = self._active
            if active is None:
                return
            if recording_id is not None and active.recording_id != recording_id:
                return
            self._active = None

        for t in active.tracks:
            t.stop()

        duration_s = time.monotonic() - active.started_monotonic
        mic_path = active.dir / "mic.wav"
        system_path = active.dir / "system.wav"
        has_system = system_path.exists() and any(t.name == "system" for t in active.tracks)

        if has_system:
            audio_path = active.dir / "mixed.wav"
            try:
                _mix_wavs(mic_path, system_path, audio_path)
            except Exception:
                log.exception("mixing failed; falling back to mic track for playback")
                audio_path = mic_path
        else:
            audio_path = mic_path

        with Session(engine) as s:
            rec = s.get(Recording, recording_id or active.recording_id)
            if rec is None:
                return
            rec.ended_at = datetime.now(timezone.utc)
            rec.duration_s = duration_s
            rec.audio_path = str(audio_path)
            rec.system_path = str(system_path) if has_system else None
            rec.status = "processing"
            s.add(rec)
            s.commit()
        log.info("recording %d stopped (%.1fs) -> processing", active.recording_id, duration_s)


def _read_mono_int16(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        n = wf.getnframes()
        raw = wf.readframes(n)
    return np.frombuffer(raw, dtype=np.int16)


def _balance_gain(x: np.ndarray) -> float:
    """Gain bringing a track's peak up to MIX_TARGET_PEAK, capped at MIX_MAX_GAIN.
    A silent track is left untouched so its noise floor isn't amplified."""
    peak = float(np.abs(x).max()) if x.size else 0.0
    if peak <= MIX_SILENCE_PEAK:
        return 1.0
    return min(MIX_MAX_GAIN, (MIX_TARGET_PEAK * 32767.0) / peak)


def _mix_wavs(a: Path, b: Path, out: Path) -> None:
    """Mix two mono 16-bit WAVs (same rate) into one. Each track is level-balanced to
    comparable loudness before summing so the (quieter) mic isn't buried under
    full-scale system audio; the sum is hard-clipped to int16 as a final safety net."""
    xa = _read_mono_int16(a).astype(np.float32)
    xb = _read_mono_int16(b).astype(np.float32)
    n = max(xa.size, xb.size)
    if xa.size < n:
        xa = np.pad(xa, (0, n - xa.size))
    if xb.size < n:
        xb = np.pad(xb, (0, n - xb.size))
    xa *= _balance_gain(xa)
    xb *= _balance_gain(xb)
    mixed = np.clip(xa + xb, -32768, 32767).astype(np.int16)
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(CAPTURE_SR)
        wf.writeframes(mixed.tobytes())
