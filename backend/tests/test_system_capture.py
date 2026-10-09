"""Native system-audio helper: probe reasons per platform, start rejection, orphan cleanup."""
import asyncio
import os
import subprocess

import pytest
from fastapi import HTTPException

from app.api import recordings as rec_api
from app.audio import system_capture


@pytest.mark.parametrize(
    "platform, code, stderr, expected",
    [
        ("macos", None, "", "BlackHole"),
        ("windows", None, "", "loopback input device"),
        ("macos", 3, "user declined TCCs", "Screen Recording"),
        ("macos", 4, "", "No display"),
        ("windows", 4, "no render device", "No audio output device"),
        ("linux", 4, "no PulseAudio/PipeWire server", "No PulseAudio or PipeWire"),
        ("linux", 2, "boom\nstream open failed", "couldn't start (stream open failed)"),
        ("windows", 3, "", "couldn't start."),
    ],
)
def test_probe_reason(platform, code, stderr, expected):
    assert expected in system_capture.probe_reason(platform, code, stderr)


def test_probe_reason_never_mentions_macos_settings_elsewhere():
    for platform in ("windows", "linux"):
        for code in (None, 2, 3, 4):
            reason = system_capture.probe_reason(platform, code, "")
            assert "System Settings" not in reason and "BlackHole" not in reason


def test_native_available_reports_probe_failure(monkeypatch, tmp_path):
    helper = tmp_path / "system-audio-capture"
    helper.write_text("")
    monkeypatch.setattr(system_capture.settings, "system_audio_sidecar", str(helper))
    monkeypatch.setattr(system_capture, "platform_name", lambda: "linux")

    def fake_run(args, **kw):
        assert args == [str(helper), "--probe"]
        return subprocess.CompletedProcess(args, 4, b"", b"no PulseAudio/PipeWire server\n")

    monkeypatch.setattr(system_capture.subprocess, "run", fake_run)
    ok, reason = system_capture.native_available()
    assert not ok and "PulseAudio or PipeWire" in reason


def test_native_available_ok(monkeypatch, tmp_path):
    helper = tmp_path / "system-audio-capture"
    helper.write_text("")
    monkeypatch.setattr(system_capture.settings, "system_audio_sidecar", str(helper))
    monkeypatch.setattr(
        system_capture.subprocess, "run", lambda args, **kw: subprocess.CompletedProcess(args, 0, b"", b"")
    )
    assert system_capture.native_available() == (True, None)


def test_start_rejects_native_with_platform_reason(monkeypatch):
    monkeypatch.setattr(rec_api.runtime, "recorder", object())
    monkeypatch.setattr(
        rec_api.system_capture, "native_available", lambda: (False, "No PulseAudio or PipeWire sound server was found.")
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(rec_api.start_recording(rec_api.StartRequest(system_source="native")))
    assert exc.value.status_code == 400
    assert "PulseAudio" in exc.value.detail and "Screen Recording" not in exc.value.detail


def test_exclude_pid_prefers_app_pid(monkeypatch):
    monkeypatch.setenv("SIRINA_APP_PID", "4242")
    assert system_capture.exclude_pid() == 4242
    monkeypatch.setenv("SIRINA_APP_PID", "")
    assert system_capture.exclude_pid() == os.getpid()


class _FakeProc:
    def __init__(self, pid, exe):
        self.pid = pid
        self.info = {"exe": exe}
        self.terminated = False

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.terminated = True


def test_kill_stale_only_touches_our_exact_binary(monkeypatch, tmp_path):
    ours = tmp_path / "bundle" / "system-audio-capture"
    ours.parent.mkdir()
    ours.write_text("")
    other = tmp_path / "elsewhere" / "system-audio-capture"  # same name, different binary
    other.parent.mkdir()
    other.write_text("")
    monkeypatch.setattr(system_capture.settings, "system_audio_sidecar", str(ours))

    orphan, lookalike, unrelated = _FakeProc(101, str(ours)), _FakeProc(102, str(other)), _FakeProc(103, None)
    import psutil

    monkeypatch.setattr(psutil, "process_iter", lambda attrs=None: [orphan, lookalike, unrelated])
    system_capture.kill_stale()
    assert orphan.terminated
    assert not lookalike.terminated and not unrelated.terminated
