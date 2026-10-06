"""Mic dropout recovery: a PortAudio input whose device vanishes mid-recording (Bluetooth
headset, iPhone Continuity mic) is reopened — on the same device if it's back, otherwise
on the default input — and the outage is filled with silence so the mic timeline stays
aligned with the system track."""
import threading
import time
import wave

import numpy as np
import pytest

import app.recording.recorder as rec_mod
from app.recording.recorder import CAPTURE_SR, _Active, _gap_frames, _Track

EARBUDS = {"name": "Soundcore A1", "max_input_channels": 1}
BUILTIN = {"name": "MacBook Pro Microphone", "max_input_channels": 1}
SPEAKER = {"name": "MacBook Pro Speakers", "max_input_channels": 0}


class FakeStream:
    def __init__(self, sd, device, callback, deliver):
        self.sd, self.device, self.callback, self.deliver = sd, device, callback, deliver

    def start(self):
        self.sd.started.append(self.device)
        if self.deliver:  # a live device delivers a 20 ms block right away
            self.callback(np.zeros((CAPTURE_SR // 50, 1), dtype=np.float32), CAPTURE_SR // 50, None, None)

    def abort(self):
        pass

    def close(self):
        pass


class FakeSD:
    """Just enough of `sounddevice`: a device list (default input last) and streams."""

    def __init__(self, devices, default, deliver=True):
        self.devices, self.default, self.deliver = devices, default, deliver
        self.started = []

    def query_devices(self, device=None, kind=None):
        if device is None and kind == "input":
            return self.devices[self.default]
        if device is not None:
            return self.devices[device]
        return self.devices

    def InputStream(self, *, device, callback, **_):
        return FakeStream(self, device, callback, self.deliver)


def _wav_seconds(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def _started_track(tmp_path, monkeypatch, name="mic"):
    sd = FakeSD([SPEAKER, EARBUDS, BUILTIN], default=1)
    monkeypatch.setattr(rec_mod, "sd", sd)
    t = _Track(name, 1, tmp_path / f"{name}.wav")
    t.start()
    return t, sd


def test_gap_frames_realigns_to_wall_clock():
    anchor = time.monotonic() - 10.0
    assert _gap_frames(anchor, 4 * CAPTURE_SR) == pytest.approx(6 * CAPTURE_SR, rel=0.01)
    assert _gap_frames(anchor, 20 * CAPTURE_SR) == 0  # never negative


def test_reopen_same_device_fills_the_gap(tmp_path, monkeypatch):
    t, sd = _started_track(tmp_path, monkeypatch)
    t.anchor -= 30.0  # the track has been running 30 s but holds only ~20 ms of audio
    t.close_stream()
    assert t.reopen(allow_fallback=True) == "Soundcore A1"
    t.stop()
    assert _wav_seconds(t.path) == pytest.approx(30.0, abs=0.2)


def test_mic_falls_back_to_default_input_when_device_is_gone(tmp_path, monkeypatch):
    t, sd = _started_track(tmp_path, monkeypatch)
    t.close_stream()
    sd.devices = [SPEAKER, BUILTIN]  # earbuds disconnected; macOS default is now built-in
    sd.default = 1
    assert t.reopen(allow_fallback=True) == "MacBook Pro Microphone"
    assert sd.started[-1] is None  # opened the default input
    t.stop()


def test_loopback_track_never_falls_back_to_the_mic(tmp_path, monkeypatch):
    t, sd = _started_track(tmp_path, monkeypatch, name="system")
    t.close_stream()
    sd.devices = [SPEAKER, BUILTIN]
    with pytest.raises(RuntimeError):
        t.reopen(allow_fallback=False)
    t.stop()


def test_recover_portaudio_reconnects_and_notes_the_dropout(tmp_path, monkeypatch):
    t, sd = _started_track(tmp_path, monkeypatch)
    monkeypatch.setattr(rec_mod, "refresh_devices", lambda: None)
    monkeypatch.setattr(rec_mod, "STALL_SECONDS", 0.05)
    sd.devices = [SPEAKER, BUILTIN]  # earbuds gone
    sd.default = 1
    t.anchor -= 60.0
    t.last_progress = time.monotonic() - 12.0
    t.health = "stalled"

    active = _Active(1, tmp_path, time.monotonic())
    active.tracks.append(t)
    worker = threading.Thread(target=active.recover_portaudio)
    worker.start()
    worker.join(timeout=5)
    active.end_monitoring()
    t.stop()

    assert t.health == "healthy"
    assert t.device_name == "MacBook Pro Microphone"
    assert len(t.events) == 1
    assert "Soundcore A1" in t.events[0] and "continued on MacBook Pro Microphone" in t.events[0]
    assert _wav_seconds(t.path) == pytest.approx(60.0, abs=0.2)


def test_device_that_keeps_stalling_moves_mic_to_default(tmp_path, monkeypatch):
    # The earbuds are still listed but their stream never delivers: the second pass must
    # stop retrying them and use the default input.
    t, sd = _started_track(tmp_path, monkeypatch)
    monkeypatch.setattr(rec_mod, "refresh_devices", lambda: None)
    monkeypatch.setattr(rec_mod, "STALL_SECONDS", 0.05)
    sd.default = 2  # built-in is the default; earbuds (index 1) stay listed
    real_stream = sd.InputStream

    def stream(*, device, callback, **kw):
        s = real_stream(device=device, callback=callback, **kw)
        s.deliver = device != 1  # the earbuds are dead
        return s

    sd.InputStream = stream
    t.last_progress = time.monotonic() - 6.0
    t.health = "stalled"

    active = _Active(1, tmp_path, time.monotonic())
    active.tracks.append(t)
    worker = threading.Thread(target=active.recover_portaudio)
    worker.start()
    worker.join(timeout=5)
    active.end_monitoring()
    t.stop()

    assert sd.started[-2:] == [1, None]  # tried the earbuds once, then the default
    assert t.device_name == "MacBook Pro Microphone"
    assert t.health == "healthy"


class FakeProc:
    """A sidecar process that emits `seconds` of audio then exits (EOF)."""

    def __init__(self, seconds):
        import io

        self.stdout = io.BytesIO(np.zeros(int(seconds * CAPTURE_SR), dtype=np.int16).tobytes())
        self.stderr = io.BytesIO(b"")

    def poll(self):
        return 0

    def terminate(self):
        pass

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


def test_sidecar_restart_fills_the_gap(tmp_path, monkeypatch):
    procs = iter([FakeProc(1.0), FakeProc(1.0)])
    monkeypatch.setattr(rec_mod.system_capture, "spawn", lambda: next(procs))
    monkeypatch.setattr(rec_mod, "MAX_SIDECAR_RESTARTS", 1)
    monkeypatch.setattr(rec_mod, "RESTART_BASE_BACKOFF", 1.5)  # the outage

    t = rec_mod._SidecarTrack("system", tmp_path / "system.wav")
    t.start()
    t._thread.join(timeout=10)  # 1s audio, EOF, 1.5s backoff, 1s audio, EOF, give up
    t.stop()

    # Without gap filling the file would hold 2.0 s. The fake emits its first second
    # instantly, so at resume (~1.5 s in) the track is ~0.5 s behind the wall clock —
    # that much silence is filled in, giving ~2.5 s.
    assert _wav_seconds(t.path) >= 2.4
    assert len(t.events) == 1 and "System audio dropped out" in t.events[0]


def test_avoid_current_skips_a_default_that_is_the_dead_device(tmp_path, monkeypatch):
    # macOS made the earbuds the default input; "use the default" would reopen them.
    t, sd = _started_track(tmp_path, monkeypatch)
    t.close_stream()
    sd.default = 1  # earbuds are the default
    assert t.reopen(allow_fallback=True, avoid_current=True) == "MacBook Pro Microphone"
    t.stop()


def test_missing_loopback_device_is_given_up_without_churning_the_mic(tmp_path, monkeypatch):
    sd = FakeSD([SPEAKER, EARBUDS, BUILTIN, {"name": "BlackHole 2ch", "max_input_channels": 2}], default=2)
    monkeypatch.setattr(rec_mod, "sd", sd)
    monkeypatch.setattr(rec_mod, "refresh_devices", lambda: None)
    monkeypatch.setattr(rec_mod, "STALL_SECONDS", 0.01)
    monkeypatch.setattr(rec_mod, "PA_REOPEN_BASE_BACKOFF", 0.01)
    monkeypatch.setattr(rec_mod, "PA_REOPEN_MAX_BACKOFF", 0.01)
    mic = _Track("mic", 1, tmp_path / "mic.wav")
    loop = _Track("system", 3, tmp_path / "system.wav")
    mic.start()
    loop.start()
    sd.devices = sd.devices[:3]  # BlackHole removed
    loop.health = "stalled"

    active = _Active(1, tmp_path, time.monotonic())
    active.tracks += [mic, loop]
    worker = threading.Thread(target=active.recover_portaudio)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive()  # gave up instead of retrying forever
    active.end_monitoring()
    mic.stop()
    loop.stop()

    assert loop.health == "stopped"
    assert mic.health == "healthy"
    assert loop.failed_reopens == rec_mod.PA_MAX_FAILED_PASSES


def test_watchdog_restarts_recovery_for_a_track_left_stalled(tmp_path, monkeypatch):
    t, sd = _started_track(tmp_path, monkeypatch)
    monkeypatch.setattr(rec_mod, "WATCHDOG_INTERVAL", 0.01)
    active = _Active(1, tmp_path, time.monotonic())
    active.tracks.append(t)
    started = threading.Event()
    monkeypatch.setattr(active, "_start_recovery", started.set)
    t.health = "stalled"  # already flagged earlier; no fresh stall will happen
    monkeypatch.setattr(active.sleep_blocker, "acquire", lambda: None)
    monkeypatch.setattr(active.sleep_blocker, "release", lambda: None)
    active.begin_monitoring()
    assert started.wait(2)
    active.end_monitoring()
    t.stop()
