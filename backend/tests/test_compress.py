"""WAV→AAC compression after processing, and the decode-back path for Re-process."""
import math
import struct
import wave

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings
from app.models import Recording
from app.processing import compress

pytestmark = pytest.mark.skipif(
    not compress.available(), reason="afconvert (macOS) not available"
)


def _write_wav(path, seconds=0.2, sr=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        n = int(sr * seconds)
        w.writeframes(
            b"".join(
                struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / sr)))
                for i in range(n)
            )
        )


@pytest.fixture
def eng():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(e)
    return e


def _recording(eng, tmp_path, wavs=("mic", "system", "mixed")):
    paths = {}
    for name in wavs:
        p = tmp_path / f"{name}.wav"
        _write_wav(p)
        paths[name] = p
    with Session(eng) as s:
        rec = Recording(
            status="ready",
            mic_path=str(paths.get("mic", "")) or None,
            system_path=str(paths.get("system", "")) or None,
            audio_path=str(paths.get("mixed", "")) or None,
        )
        s.add(rec)
        s.commit()
        s.refresh(rec)
        return rec.id


def test_compress_and_restore_round_trip(eng, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "compress_audio", True)
    rid = _recording(eng, tmp_path)

    assert compress.compress_recording(rid, eng) is True
    with Session(eng) as s:
        rec = s.get(Recording, rid)
        for p in (rec.mic_path, rec.system_path, rec.audio_path):
            assert p.endswith(".m4a")
    assert not list(tmp_path.glob("*.wav"))  # originals deleted
    assert len(list(tmp_path.glob("*.m4a"))) == 3

    assert compress.restore_wavs(rid, eng) is True
    with Session(eng) as s:
        rec = s.get(Recording, rid)
        for p in (rec.mic_path, rec.system_path, rec.audio_path):
            assert p.endswith(".wav")
    assert not list(tmp_path.glob("*.m4a"))
    with wave.open(str(tmp_path / "mixed.wav")) as w:  # decodable, sane params
        assert w.getframerate() == 16000 and w.getnchannels() == 1


def test_compress_disabled_by_setting(eng, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "compress_audio", False)
    rid = _recording(eng, tmp_path)
    assert compress.compress_recording(rid, eng) is False
    assert len(list(tmp_path.glob("*.wav"))) == 3


def test_compress_keeps_wav_when_encode_fails(eng, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "compress_audio", True)
    rid = _recording(eng, tmp_path, wavs=("mic",))
    bad = tmp_path / "mixed.wav"
    bad.write_bytes(b"not a wav")
    with Session(eng) as s:
        rec = s.get(Recording, rid)
        rec.audio_path = str(bad)
        s.add(rec)
        s.commit()

    compress.compress_recording(rid, eng)
    with Session(eng) as s:
        rec = s.get(Recording, rid)
        assert rec.mic_path.endswith(".m4a")  # good track converted
        assert rec.audio_path == str(bad)  # bad track untouched
    assert bad.exists()


def test_restore_noop_without_compressed_tracks(eng, tmp_path):
    rid = _recording(eng, tmp_path)
    assert compress.restore_wavs(rid, eng) is True  # nothing to do, still fine
    assert len(list(tmp_path.glob("*.wav"))) == 3


def test_restore_fails_when_file_missing(eng, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "compress_audio", True)
    rid = _recording(eng, tmp_path, wavs=("mic",))
    assert compress.compress_recording(rid, eng) is True
    (tmp_path / "mic.m4a").unlink()
    assert compress.restore_wavs(rid, eng) is False
    with Session(eng) as s:  # path left as-is so the failure is visible, not hidden
        assert s.get(Recording, rid).mic_path.endswith(".m4a")
