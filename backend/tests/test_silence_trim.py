"""Silence detection + WAV trimming for the post-stop trim prompt."""
import wave

import numpy as np
import app.recording.recorder as rec_mod
from app.audio.trim import detect_trim, trim_wav_window
from app.models import Recording
from app.recording.recorder import CAPTURE_SR, apply_trim
from sqlmodel import Session, SQLModel, create_engine


def _write_wav(path, segments) -> None:
    """segments: list of (seconds, amplitude int16). Concatenated into one mono WAV."""
    frames = []
    for secs, amp in segments:
        n = int(secs * CAPTURE_SR)
        frames.append(np.full(n, amp, dtype=np.int16))
    data = np.concatenate(frames) if frames else np.zeros(0, dtype=np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(CAPTURE_SR)
        w.writeframes(data.tobytes())


def _dur(path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def test_detect_trailing_silence_on_system_track(tmp_path):
    # System track: 5s silence, 10s speech, 120s silence (forgot to stop).
    sysf = tmp_path / "system.wav"
    _write_wav(sysf, [(5, 0), (10, 8000), (120, 0)])
    # Mic keeps capturing quiet room noise to the very end (should NOT block trailing trim).
    mic = tmp_path / "mic.wav"
    _write_wav(mic, [(135, 200)])

    out = detect_trim(mic, sysf, min_silence_s=60)
    assert out is not None
    assert 4.0 < out["leading_s"] < 6.0
    assert out["trailing_s"] > 100
    assert 14.0 < out["end_s"] < 16.0


def test_no_suggestion_when_silence_below_threshold(tmp_path):
    sysf = tmp_path / "system.wav"
    _write_wav(sysf, [(2, 0), (30, 8000), (3, 0)])
    assert detect_trim(None, sysf, min_silence_s=60) is None


def test_fully_silent_returns_none(tmp_path):
    sysf = tmp_path / "system.wav"
    _write_wav(sysf, [(60, 0)])
    assert detect_trim(None, sysf, min_silence_s=10) is None


def test_trim_wav_window_slices_correctly(tmp_path):
    src = tmp_path / "s.wav"
    _write_wav(src, [(2, 0), (4, 9000), (2, 0)])  # 8s total
    dst = tmp_path / "d.wav"
    trim_wav_window(src, dst, 2.0, 6.0)
    assert abs(_dur(dst) - 4.0) < 0.05


def test_apply_trim_updates_tracks_and_duration(tmp_path, monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(rec_mod, "engine", eng)
    monkeypatch.setattr(rec_mod.settings, "app_data_dir", str(tmp_path))
    with Session(eng) as s:
        r = Recording(status="processing", pending_trim='{"start_s": 5, "end_s": 15}')
        s.add(r)
        s.commit()
        s.refresh(r)
        rid = r.id

    rec_dir = rec_mod.settings.recordings_dir / str(rid)
    rec_dir.mkdir(parents=True)
    _write_wav(rec_dir / "mic.wav", [(20, 5000)])
    _write_wav(rec_dir / "system.wav", [(20, 5000)])

    new_dur = apply_trim(rid, 5.0, 15.0)
    assert abs(new_dur - 10.0) < 0.05
    assert abs(_dur(rec_dir / "mic.wav") - 10.0) < 0.05
    assert (rec_dir / "mixed.wav").exists()
    with Session(eng) as s:
        r = s.get(Recording, rid)
        assert r.pending_trim is None
        assert abs(r.duration_s - 10.0) < 0.05
        assert r.audio_path.endswith("mixed.wav")
