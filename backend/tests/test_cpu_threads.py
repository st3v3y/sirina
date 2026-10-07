"""CPU-engine thread default: performance cores on Apple Silicon, configured value wins."""
from app.transcribe import whisper


def test_configured_value_wins(monkeypatch):
    monkeypatch.setattr(whisper, "_sysctl_int", lambda name: 6)
    assert whisper.default_cpu_threads(3) == 3


def test_performance_cores_on_apple_silicon(monkeypatch):
    monkeypatch.setattr(whisper, "_sysctl_int", lambda name: 6 if name == "hw.perflevel0.physicalcpu" else None)
    monkeypatch.setattr(whisper.os, "cpu_count", lambda: 8)
    assert whisper.default_cpu_threads(0) == 6


def test_all_cores_without_perf_levels(monkeypatch):
    monkeypatch.setattr(whisper, "_sysctl_int", lambda name: None)
    monkeypatch.setattr(whisper.os, "cpu_count", lambda: 8)
    assert whisper.default_cpu_threads(0) == 8


def test_real_sysctl_returns_positive_or_none():
    value = whisper._sysctl_int("hw.perflevel0.physicalcpu")
    assert value is None or value > 0
