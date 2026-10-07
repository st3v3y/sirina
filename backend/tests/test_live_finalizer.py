"""Transcription during recording: complete windows only, stop safety, Low Power pause."""
import asyncio

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.processing.windows as windows_mod
import app.recording.live as live_mod
from app.models import Recording, Segment
from app.processing.windows import Track
from app.recording.live import LiveFinalizer
from app.transcribe.whisper import TLine

MIC = Track("mic", "You", "sky", "/mic.wav")
SYS = Track("system", "Speaker 1", "rose", "/sys.wav")


@pytest.fixture()
def db(monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        rec = Recording(status="recording")
        s.add(rec)
        s.commit()
        s.refresh(rec)
        rid = rec.id
    monkeypatch.setattr(live_mod, "db_engine", eng)
    monkeypatch.setattr(windows_mod, "speech_regions", lambda p, a=0.0, b=None: [(0.0, 10_000.0)])
    return eng, rid


def _segs(eng, rid):
    with Session(eng) as s:
        return s.exec(select(Segment).where(Segment.recording_id == rid)).all()


async def _fake_transcribe(path, a, b, language=None):
    return [TLine(a + 0.5, a + 1.0, f"{path}@{a:.0f}", [(a + 0.5, a + 1.0, "w")])], "en"


def test_commits_only_complete_windows(db):
    eng, rid = db

    async def run():
        live = LiveFinalizer(rid, [MIC, SYS], lambda: 14.0, _fake_transcribe,
                             poll_s=0.01, target_s=4, low_power=lambda: False)
        live.start()
        await asyncio.sleep(0.2)
        await live.stop()
        return live

    live = asyncio.run(run())
    # 12 s safely on disk → windows end at 4 and 8; the open tail (8–12) waits for more audio.
    assert live.final_until_s == 8
    assert sorted({x.start_ts for x in _segs(eng, rid)}) == [0.5, 4.5]
    with Session(eng) as s:
        assert s.get(Recording, rid).final_until_s == 8


def test_no_commit_after_stop_with_window_in_flight(db):
    eng, rid = db
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_transcribe(path, a, b, language=None):
        started.set()
        await release.wait()
        return await _fake_transcribe(path, a, b, language)

    async def run():
        live = LiveFinalizer(rid, [MIC], lambda: 14.0, slow_transcribe,
                             poll_s=0.01, target_s=4, low_power=lambda: False)
        live.start()
        await started.wait()
        await live.stop()  # recording stops while the first window is transcribing
        release.set()
        await asyncio.sleep(0.05)

    asyncio.run(run())
    assert _segs(eng, rid) == []  # nothing committed after stop; the job redoes it


def test_guarded_commit_refuses_after_stop(db):
    eng, rid = db
    live = LiveFinalizer(rid, [MIC], lambda: 0.0, _fake_transcribe, low_power=lambda: False)
    asyncio.run(live.stop())
    assert live._commit(eng, rid, 0, 4, [(MIC, [TLine(1, 2, "x")])], None) == 0
    assert _segs(eng, rid) == []


def test_pauses_in_low_power_mode(db):
    eng, rid = db
    calls = []

    async def counting(path, a, b, language=None):
        calls.append(a)
        return await _fake_transcribe(path, a, b, language)

    async def run():
        live = LiveFinalizer(rid, [MIC], lambda: 30.0, counting,
                             poll_s=0.01, target_s=4, low_power=lambda: True)
        live.start()
        await asyncio.sleep(0.1)
        snap = live.snapshot()
        await live.stop()
        return snap

    snap = asyncio.run(run())
    assert calls == [] and snap["paused"] == "low_power"


def test_turned_off_starts_no_new_window(db):
    eng, rid = db

    async def run():
        live = LiveFinalizer(rid, [MIC], lambda: 30.0, _fake_transcribe,
                             poll_s=0.01, target_s=4, low_power=lambda: False)
        live.enabled = False
        live.start()
        await asyncio.sleep(0.1)
        await live.stop()

    asyncio.run(run())
    assert _segs(eng, rid) == []
