"""recover_orphaned finalizes a recording left in `recording` by a crash before stop()."""
import wave

import app.recording.recorder as rec_mod
from app.models import Recording
from app.recording.recorder import CAPTURE_SR, recover_orphaned
from sqlmodel import Session, SQLModel, create_engine


def _write_wav(path, seconds: float) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(CAPTURE_SR)
        w.writeframes(b"\x01\x00" * int(seconds * CAPTURE_SR))


def _setup(tmp_path, monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(rec_mod, "engine", eng)
    monkeypatch.setattr(rec_mod.settings, "app_data_dir", str(tmp_path))
    return eng


def test_recovers_two_track_orphan(tmp_path, monkeypatch):
    eng = _setup(tmp_path, monkeypatch)
    with Session(eng) as s:
        r = Recording(status="recording")
        s.add(r)
        s.commit()
        s.refresh(r)
        rid = r.id

    rec_dir = rec_mod.settings.recordings_dir / str(rid)
    rec_dir.mkdir(parents=True)
    _write_wav(rec_dir / "mic.wav", 3.0)
    _write_wav(rec_dir / "system.wav", 2.5)

    assert recover_orphaned(rid) is True

    with Session(eng) as s:
        r = s.get(Recording, rid)
        assert r.status == "processing"
        assert r.audio_path.endswith("mixed.wav")  # both tracks present -> mixed
        assert r.mic_path and r.system_path
        assert r.ended_at is not None
        assert abs(r.duration_s - 3.0) < 0.05  # longer of the two tracks
    assert (rec_dir / "mixed.wav").exists()


def test_recovers_mic_only_orphan(tmp_path, monkeypatch):
    eng = _setup(tmp_path, monkeypatch)
    with Session(eng) as s:
        r = Recording(status="recording")
        s.add(r)
        s.commit()
        s.refresh(r)
        rid = r.id

    rec_dir = rec_mod.settings.recordings_dir / str(rid)
    rec_dir.mkdir(parents=True)
    _write_wav(rec_dir / "mic.wav", 1.5)

    assert recover_orphaned(rid) is True
    with Session(eng) as s:
        r = s.get(Recording, rid)
        assert r.status == "processing"
        assert r.audio_path.endswith("mic.wav")  # no system track -> mic is the audio
        assert r.system_path is None


def test_no_audio_returns_false(tmp_path, monkeypatch):
    eng = _setup(tmp_path, monkeypatch)
    with Session(eng) as s:
        r = Recording(status="recording")
        s.add(r)
        s.commit()
        s.refresh(r)
        rid = r.id
    (rec_mod.settings.recordings_dir / str(rid)).mkdir(parents=True)

    assert recover_orphaned(rid) is False
    with Session(eng) as s:
        assert s.get(Recording, rid).status == "recording"  # untouched
