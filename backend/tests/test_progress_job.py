"""Progress plumbing: stages advance through _process and clear afterward."""
import asyncio

import app.processing.job as job_mod
from app.models import Recording, Segment
from app.processing.job import TranscriptionProcessor
from app.transcribe.whisper import TLine
from sqlmodel import Session, SQLModel, create_engine, select


class FakeEngine:
    name = "fake"

    def __init__(self):
        self._loaded = False
        self.calls = []

    def is_loaded(self):
        return self._loaded

    async def load(self):
        self._loaded = True

    async def transcribe_file(self, path, *, word_timestamps=True, progress_cb=None):
        self.calls.append(path)
        if progress_cb:
            progress_cb(5.0, 10.0)  # mid
            progress_cb(10.0, 10.0)  # end
        return [TLine(0.0, 1.0, "hello world")], "en"


def _setup(tmp_path):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    mic = tmp_path / "mic.wav"; mic.write_bytes(b"x")
    sysf = tmp_path / "system.wav"; sysf.write_bytes(b"x")
    mixed = tmp_path / "mixed.wav"; mixed.write_bytes(b"x")
    with Session(eng) as s:
        rec = Recording(status="processing", audio_path=str(mixed), mic_path=str(mic), system_path=str(sysf))
        s.add(rec)
        s.commit()
        s.refresh(rec)
        rid = rec.id
    return eng, rid


def test_process_advances_to_done_and_writes_segments(tmp_path, monkeypatch):
    eng, rid = _setup(tmp_path)
    monkeypatch.setattr(job_mod, "engine", eng)
    proc = TranscriptionProcessor(FakeEngine(), pipeline=None, diarizer=None)

    asyncio.run(proc._process(rid))

    # Stage reached "done" (terminal in _process; _run's finally would clear it).
    prog = proc.progress_for(rid)
    assert prog["stage"] == "done"
    assert prog["fraction"] == 1.0
    assert prog["elapsed_s"] is not None
    with Session(eng) as s:
        segs = s.exec(select(Segment).where(Segment.recording_id == rid)).all()
        assert len(segs) == 2  # mic "You" + system "Speaker 1", one line each
        rec = s.get(Recording, rid)
        assert rec.status == "ready"


def test_two_track_progress_weighting(tmp_path, monkeypatch):
    eng, rid = _setup(tmp_path)
    monkeypatch.setattr(job_mod, "engine", eng)
    proc = TranscriptionProcessor(FakeEngine(), pipeline=None, diarizer=None)

    seen = []
    orig = proc._set_progress

    def spy(recording_id, stage, fraction=None, **kwargs):
        seen.append((stage, fraction))
        orig(recording_id, stage, fraction, **kwargs)

    monkeypatch.setattr(proc, "_set_progress", spy)
    asyncio.run(proc._process(rid))

    fracs = [f for stage, f in seen if stage == "transcribing" and f is not None]
    # mic pass maps into 0–0.5, system pass into 0.5–1.0.
    assert max(f for f in fracs if f <= 0.5) == 0.5  # mic end
    assert max(fracs) == 1.0  # system end


def test_estimated_fraction_and_elapsed():
    proc = TranscriptionProcessor(FakeEngine(), pipeline=None, diarizer=None)
    import time as _t
    proc._started[7] = _t.monotonic() - 10.0  # pretend 10s elapsed
    # Non-streaming engine sets est_total; progress_for derives an estimated fraction.
    proc._set_progress(7, "transcribing", None, est_total=100.0)
    p = proc.progress_for(7)
    assert p["estimated"] is True
    assert 0.0 < p["fraction"] <= 0.95  # ~10/100, capped at 0.95
    assert p["elapsed_s"] >= 10.0

    # Real fraction (streaming) is never treated as an estimate.
    proc._set_progress(7, "transcribing", 0.4)
    p = proc.progress_for(7)
    assert p["estimated"] is False
    assert p["fraction"] == 0.4


class FakeDiarizer:
    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    async def diarize(self, path):
        self.calls += 1
        return []  # no turns → would fall back to baseline anyway


def test_cancel_diarization_keeps_baseline_and_skips_diarize(tmp_path, monkeypatch):
    eng, rid = _setup(tmp_path)
    monkeypatch.setattr(job_mod, "engine", eng)
    diar = FakeDiarizer()
    proc = TranscriptionProcessor(FakeEngine(), pipeline=None, diarizer=diar)
    proc.cancel_diarization(rid)  # cancel before processing starts

    asyncio.run(proc._process(rid))

    # Diarization was skipped entirely; baseline transcript persisted.
    assert diar.calls == 0
    with Session(eng) as s:
        from app.models import Speaker
        labels = sorted(sp.label for sp in s.exec(select(Speaker).where(Speaker.recording_id == rid)).all())
        assert labels == ["Speaker 1", "You"]  # baseline two-track split
        rec = s.get(Recording, rid)
        assert rec.status == "ready"


def test_write_tracks_is_idempotent(tmp_path, monkeypatch):
    eng, rid = _setup(tmp_path)
    monkeypatch.setattr(job_mod, "engine", eng)
    proc = TranscriptionProcessor(FakeEngine(), pipeline=None, diarizer=None)
    proc._write_tracks(rid, [("You", "sky", [TLine(0, 1, "a")])], "en")
    proc._write_tracks(rid, [("Alice", "rose", [TLine(0, 1, "a"), TLine(1, 2, "b")])], "en")
    with Session(eng) as s:
        from app.models import Speaker
        spk = s.exec(select(Speaker).where(Speaker.recording_id == rid)).all()
        segs = s.exec(select(Segment).where(Segment.recording_id == rid)).all()
        assert [x.label for x in spk] == ["Alice"]  # replaced, not appended
        assert len(segs) == 2


def _write_wav(path, sr, samples):
    import wave, numpy as np
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(np.asarray(samples, dtype=np.int16).tobytes())


def test_silent_system_track_skipped(tmp_path, monkeypatch):
    """A silent system track must not be transcribed (no hallucinated 'Others')."""
    import numpy as np
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    sr = 16000
    mic = tmp_path / "mic.wav"; _write_wav(mic, sr, (np.random.randn(sr) * 3000).astype(np.int16))  # has audio
    sysf = tmp_path / "system.wav"; _write_wav(sysf, sr, np.zeros(sr, dtype=np.int16))  # silent
    mixed = tmp_path / "mixed.wav"; _write_wav(mixed, sr, (np.random.randn(sr) * 3000).astype(np.int16))
    with Session(eng) as s:
        rec = Recording(status="processing", audio_path=str(mixed), mic_path=str(mic), system_path=str(sysf))
        s.add(rec); s.commit(); s.refresh(rec); rid = rec.id

    monkeypatch.setattr(job_mod, "engine", eng)
    proc = TranscriptionProcessor(FakeEngine(), pipeline=None, diarizer=None)
    asyncio.run(proc._process(rid))

    with Session(eng) as s:
        from app.models import Speaker
        labels = [sp.label for sp in s.exec(select(Speaker).where(Speaker.recording_id == rid)).all()]
        assert labels == ["You"]  # only the mic; silent system produced no speaker
