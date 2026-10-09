"""The processing job: windowed two-track finalization, drafts, resume, stop, fallback."""
import asyncio
import os
import wave

import numpy as np
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.processing.job as job_mod
import app.processing.windows as windows_mod
from app.config import settings
from app.models import Recording, Segment, Speaker
from app.processing.job import TranscriptionProcessor
from app.transcribe.speech_helper import HelperError
from app.transcribe.whisper import TLine

SR = 16000
DUR = 10.0


class FakeEngine:
    name = "fake"

    def __init__(self, fail_after: int | None = None):
        self._loaded = False
        self.calls = []
        self.fail_after = fail_after

    def is_loaded(self):
        return self._loaded

    async def load(self):
        self._loaded = True

    async def transcribe_window(self, path, start_s, end_s, *, language=None):
        if self.fail_after is not None and len(self.calls) >= self.fail_after:
            raise HelperError("speech helper exited")
        self.calls.append((os.path.basename(path), start_s, end_s))
        a = start_s + 0.5
        return [TLine(a, a + 1.0, f"hello {start_s:.0f}", [(a, a + 0.5, "hello"), (a + 0.5, a + 1.0, f"{start_s:.0f}")])], "en"


def _wav(path, samples):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.asarray(samples, dtype=np.int16).tobytes())


def _noise():
    return (np.random.default_rng(0).standard_normal(int(SR * DUR)) * 3000).astype(np.int16)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    for name in ("mic.wav", "system.wav", "mixed.wav"):
        _wav(tmp_path / name, _noise())
    with Session(eng) as s:
        rec = Recording(
            status="processing",
            audio_path=str(tmp_path / "mixed.wav"),
            mic_path=str(tmp_path / "mic.wav"),
            system_path=str(tmp_path / "system.wav"),
            duration_s=DUR,
        )
        s.add(rec)
        s.commit()
        s.refresh(rec)
        rid = rec.id
    monkeypatch.setattr(job_mod, "engine", eng)
    monkeypatch.setattr(settings, "compress_audio", False)
    monkeypatch.setattr(settings, "transcribe_chunk_seconds", 4)
    # Continuous "speech" everywhere, so windows cut at the targets.
    monkeypatch.setattr(windows_mod, "speech_regions", lambda path, a=0.0, b=None: [(0.0, DUR)])
    return eng, rid, tmp_path


def _segs(eng, rid):
    with Session(eng) as s:
        return s.exec(select(Segment).where(Segment.recording_id == rid).order_by(Segment.start_ts)).all()


def test_process_finalizes_both_tracks_window_by_window(env):
    eng, rid, _ = env
    fake = FakeEngine()
    proc = TranscriptionProcessor(fake, pipeline=None, diarizer=None)
    asyncio.run(proc._process(rid))

    # Two windows (cut at ~4 s), each transcribing mic then system before committing.
    assert [c[0] for c in fake.calls] == ["mic.wav", "system.wav", "mic.wav", "system.wav"]
    assert fake.calls[0][1:] == (0.0, 4) and fake.calls[2][1:] == (4, DUR)
    prog = proc.progress_for(rid)
    assert prog["stage"] == "done" and prog["fraction"] == 1.0 and prog["final_until_s"] == DUR
    with Session(eng) as s:
        rec = s.get(Recording, rid)
        assert rec.status == "ready" and rec.final_until_s == DUR and rec.language == "en"
    segs = _segs(eng, rid)
    assert len(segs) == 4 and not any(x.is_draft for x in segs) and all(x.words for x in segs)


def test_silent_system_track_skipped(env):
    eng, rid, tmp = env
    _wav(tmp / "system.wav", np.zeros(int(SR * DUR), dtype=np.int16))
    fake = FakeEngine()
    asyncio.run(TranscriptionProcessor(fake, pipeline=None, diarizer=None)._process(rid))
    assert {c[0] for c in fake.calls} == {"mic.wav"}
    with Session(eng) as s:
        assert [sp.label for sp in s.exec(select(Speaker)).all()] == ["You"]


def test_resume_after_restart_starts_at_final_point(env):
    eng, rid, _ = env
    with Session(eng) as s:
        rec = s.get(Recording, rid)
        rec.final_until_s = 4.0
        rec.language = "de"
        s.add(rec)
        s.commit()
    fake = FakeEngine()
    asyncio.run(TranscriptionProcessor(fake, pipeline=None, diarizer=None)._process(rid))
    assert all(c[1] >= 4.0 for c in fake.calls) and fake.calls


def test_draft_first_then_replaced_by_final(env):
    eng, rid, _ = env
    seen_drafts = []

    async def drafter(path, a, b, lang):
        return [TLine(1.0, 2.0, "draft one"), TLine(6.0, 7.0, "draft two")]

    class Peeking(FakeEngine):
        async def transcribe_window(self, path, start_s, end_s, *, language=None):
            seen_drafts.append(sum(1 for x in _segs(eng, rid) if x.is_draft))
            return await super().transcribe_window(path, start_s, end_s, language=language)

    asyncio.run(TranscriptionProcessor(Peeking(), pipeline=None, diarizer=None, drafter=drafter)._process(rid))
    assert seen_drafts[0] == 4  # 2 drafts × 2 tracks existed before the first window
    assert not any(x.is_draft for x in _segs(eng, rid))  # all replaced by the end


def test_stop_midway_keeps_finals_and_marked_drafts(env):
    eng, rid, _ = env
    proc = None

    async def drafter(path, a, b, lang):
        return [TLine(6.0, 7.0, "late draft")]

    class StopAfterFirstWindow(FakeEngine):
        async def transcribe_window(self, path, start_s, end_s, *, language=None):
            out = await super().transcribe_window(path, start_s, end_s, language=language)
            if len(self.calls) == 2:
                proc.cancel_processing(rid)
            return out

    proc = TranscriptionProcessor(StopAfterFirstWindow(), pipeline=None, diarizer=None, drafter=drafter)
    asyncio.run(proc._process(rid))
    segs = _segs(eng, rid)
    assert [x.is_draft for x in segs if x.start_ts < 4] == [False, False]
    assert [x.text for x in segs if x.is_draft] == ["late draft", "late draft"]
    with Session(eng) as s:
        rec = s.get(Recording, rid)
        assert rec.status == "ready" and rec.final_until_s == 4


def test_whisperkit_load_failure_falls_back_to_cpu(env, monkeypatch):
    eng, rid, _ = env

    class BrokenWK(FakeEngine):
        name = "whisperkit"

        async def load(self):
            raise RuntimeError("offline")

    cpu = FakeEngine()
    monkeypatch.setattr(job_mod, "FasterWhisperWorker", lambda: cpu)
    proc = TranscriptionProcessor(BrokenWK(), pipeline=None, diarizer=None)
    asyncio.run(proc._process(rid))
    assert cpu.calls
    with Session(eng) as s:
        rec = s.get(Recording, rid)
        assert rec.status == "ready" and "CPU engine" in (rec.warning or "")


def test_helper_failure_midway_finishes_on_cpu(env, monkeypatch):
    eng, rid, _ = env
    wk = FakeEngine(fail_after=2)
    wk.name = "whisperkit"
    cpu = FakeEngine()
    monkeypatch.setattr(job_mod, "FasterWhisperWorker", lambda: cpu)
    asyncio.run(TranscriptionProcessor(wk, pipeline=None, diarizer=None)._process(rid))
    assert len(wk.calls) == 2 and len(cpu.calls) == 2  # window 2 ran on the CPU engine
    with Session(eng) as s:
        assert s.get(Recording, rid).final_until_s == DUR


class FakeDiarizer:
    def __init__(self, turns=None):
        self.calls = 0
        self.turns = turns or []

    def is_available(self):
        return True

    async def diarize(self, path):
        self.calls += 1
        return self.turns


def test_cancel_diarization_keeps_baseline_and_skips_diarize(env):
    eng, rid, _ = env
    diar = FakeDiarizer()
    proc = TranscriptionProcessor(FakeEngine(), pipeline=None, diarizer=diar)
    proc.cancel_diarization(rid)
    asyncio.run(proc._process(rid))
    assert diar.calls == 0
    with Session(eng) as s:
        labels = sorted(sp.label for sp in s.exec(select(Speaker).where(Speaker.recording_id == rid)).all())
        assert labels == ["Speaker 1", "You"]


def test_diarization_uses_stored_word_timings(env, monkeypatch):
    eng, rid, _ = env
    seen = {}
    real = job_mod.diarize_lines

    def spy(lines, turns):
        seen["words"] = [w for ln in lines for w in ln.words]
        return real(lines, turns)

    monkeypatch.setattr(job_mod, "diarize_lines", spy)

    diar = FakeDiarizer([(0.0, 5.0, "A"), (5.0, 10.0, "B")])
    asyncio.run(TranscriptionProcessor(FakeEngine(), pipeline=None, diarizer=diar)._process(rid))
    assert diar.calls == 1 and seen["words"]  # rebuilt from the DB, words intact


def test_estimated_fraction_and_elapsed():
    proc = TranscriptionProcessor(FakeEngine(), pipeline=None, diarizer=None)
    import time as _t

    proc._started[7] = _t.monotonic() - 10.0
    proc._set_progress(7, "transcribing", None, est_total=100.0)
    proc._progress[7]["stage_started"] -= 5.0  # Windows' clock may not tick between two calls
    p = proc.progress_for(7)
    assert p["estimated"] is True and 0.0 < p["fraction"] <= 0.95 and p["elapsed_s"] >= 10.0
    proc._set_progress(7, "transcribing", 0.4)
    assert proc.progress_for(7)["estimated"] is False


def test_write_tracks_is_idempotent(env):
    eng, rid, _ = env
    proc = TranscriptionProcessor(FakeEngine(), pipeline=None, diarizer=None)
    proc._write_tracks(rid, [("You", "sky", [TLine(0, 1, "a")])], "en")
    proc._write_tracks(rid, [("Alice", "rose", [TLine(0, 1, "a"), TLine(1, 2, "b")])], "en")
    with Session(eng) as s:
        assert [x.label for x in s.exec(select(Speaker).where(Speaker.recording_id == rid)).all()] == ["Alice"]
    assert len(_segs(eng, rid)) == 2


def test_split_speakers_live_relabels_final_lines(env):
    eng, rid, tmp = env
    from app.processing import windows as w

    you = w.Track("mic", "You", "sky", str(tmp / "mic.wav"))
    other = w.Track("system", "Speaker 1", "rose", str(tmp / "system.wav"))
    w.commit_window(eng, rid, 0, 100, [
        (you, [TLine(0.5, 1.0, "hi", [(0.5, 1.0, "hi")])]),
        (other, [TLine(2.0, 40.0, "alpha", [(2.0, 40.0, "alpha")]), TLine(50.0, 90.0, "beta", [(50.0, 90.0, "beta")])]),
    ], "en")
    diar = FakeDiarizer([(0.0, 45.0, "A"), (45.0, 100.0, "B")])
    proc = TranscriptionProcessor(FakeEngine(), pipeline=None, diarizer=diar)
    asyncio.run(proc.split_speakers_live(rid, True, str(tmp / "mic.wav"), str(tmp / "system.wav")))
    with Session(eng) as s:
        labels = sorted(sp.label for sp in s.exec(select(Speaker).where(Speaker.recording_id == rid)).all())
        rec = s.get(Recording, rid)
    assert labels == ["Speaker 1", "Speaker 2", "You"]
    assert rec.final_until_s == 100  # the boundary is untouched by relabelling
    assert all(x.words for x in _segs(eng, rid))  # word timings survive for the final split
