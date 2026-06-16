"""Local recorder: captures mic (and optional system) audio to WAV files on disk.

Runs NO inference — during a recording the only work is downmixing to mono and
writing 16-bit PCM. A separate processing job (later change) transcribes the
finished files.
"""
from __future__ import annotations

import asyncio
import logging
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import sounddevice as sd
from sqlmodel import Session

from ..audio.local import find_device
from ..config import settings
from ..db import engine
from ..models import Recording

log = logging.getLogger(__name__)

CAPTURE_SR = 48_000  # capture both tracks at a common rate so they mix cleanly


def _recordings_dir() -> Path:
    base = Path(settings.db_path).resolve().parent / "recordings"
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
        level = max((t.level for t in a.tracks), default=0.0)
        return {
            "id": a.recording_id,
            "elapsed_s": time.monotonic() - a.started_monotonic,
            "level": level,
        }

    async def start(
        self,
        device: str | int | None,
        system_device: str | int | None,
        label: str | None,
        title: str | None,
    ) -> int:
        async with self._lock:
            if self._active is not None:
                raise RuntimeError(
                    f"Already recording #{self._active.recording_id}; stop it first"
                )

            mic_dev = find_device(device)
            sys_dev = find_device(system_device) if system_device else None

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
            sys_track: _Track | None = None
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


def _mix_wavs(a: Path, b: Path, out: Path) -> None:
    """Sum two mono 16-bit WAVs (same rate) into one, hard-clipping to int16."""
    xa = _read_mono_int16(a).astype(np.int32)
    xb = _read_mono_int16(b).astype(np.int32)
    n = max(xa.size, xb.size)
    if xa.size < n:
        xa = np.pad(xa, (0, n - xa.size))
    if xb.size < n:
        xb = np.pad(xb, (0, n - xb.size))
    mixed = np.clip(xa + xb, -32768, 32767).astype(np.int16)
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(CAPTURE_SR)
        wf.writeframes(mixed.tobytes())
