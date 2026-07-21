"""A diarization failure is surfaced as a recording warning, not silently swallowed."""
import asyncio

import app.processing.job as job_mod
from app.models import Recording, Speaker
from app.processing.job import TranscriptionProcessor
from app.transcribe.whisper import TLine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


class FakeEngine:
    name = "fake"

    def __init__(self):
        self._loaded = False

    def is_loaded(self):
        return self._loaded

    async def load(self):
        self._loaded = True

    async def transcribe_file(self, path, *, word_timestamps=True, progress_cb=None):
        if progress_cb:
            progress_cb(10.0, 10.0)
        return [TLine(0.0, 1.0, "hello")], "en"


class FailingDiarizer:
    def is_available(self):
        return True

    async def diarize(self, path):
        raise RuntimeError("model terms not accepted")


def _setup(tmp_path):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    for name in ("mic.wav", "system.wav", "mixed.wav"):
        (tmp_path / name).write_bytes(b"x")
    with Session(eng) as s:
        rec = Recording(
            status="processing",
            audio_path=str(tmp_path / "mixed.wav"),
            mic_path=str(tmp_path / "mic.wav"),
            system_path=str(tmp_path / "system.wav"),
        )
        s.add(rec)
        s.commit()
        s.refresh(rec)
        rid = rec.id
    return eng, rid


def test_diarization_failure_sets_warning(tmp_path, monkeypatch):
    eng, rid = _setup(tmp_path)
    monkeypatch.setattr(job_mod, "engine", eng)
    # Non-silent tracks so transcription + diarization actually run.
    monkeypatch.setattr(job_mod, "_is_silent", lambda p: False)
    proc = TranscriptionProcessor(FakeEngine(), pipeline=None, diarizer=FailingDiarizer())

    asyncio.run(proc._process(rid))

    with Session(eng) as s:
        rec = s.get(Recording, rid)
        assert rec.status == "ready"  # transcript still finalizes
        assert rec.warning and "Speaker splitting couldn't run" in rec.warning
        # Fell back to the baseline two-track split (You + Speaker 1), not a crash.
        labels = sorted(sp.label for sp in s.exec(select(Speaker).where(Speaker.recording_id == rid)).all())
        assert labels == ["Speaker 1", "You"]
