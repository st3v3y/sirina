"""Regression tests for the critical-path review round: two-pointer cluster
assignment, enqueue dedupe, delete-while-processing guards, enroll idempotency
and withdrawal, and compression path-aliasing."""
import asyncio
import json
import random
import wave

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.api.recordings import (
    SpeakerRenameRequest,
    delete_recording,
    rename_speaker,
)
from app.config import settings
from app.models import Person, Recording, Speaker
from app.processing import compress
from app.processing.diarize import assign_clusters
from app.processing.job import TranscriptionProcessor


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


# --- assign_clusters: optimized merge must match the brute-force reference ---


def _brute_force(units, turns):
    labels = []
    for start, end, _text in units:
        best_label, best_overlap = None, 0.0
        for t_start, t_end, cluster in turns:
            overlap = min(end, t_end) - max(start, t_start)
            if overlap > best_overlap:
                best_overlap, best_label = overlap, cluster
        labels.append(best_label or "SPEAKER_00")
    return labels


def test_assign_clusters_matches_brute_force_on_random_data():
    rng = random.Random(42)
    turns = []
    t = 0.0
    for i in range(200):
        dur = rng.uniform(0.5, 8.0)
        turns.append((t, t + dur, f"SPEAKER_{i % 4}"))
        t += dur + rng.uniform(0.0, 2.0)  # gaps between turns
    units = []
    u = 0.2
    while u < t:
        dur = rng.uniform(0.1, 1.5)
        units.append((u, u + dur, "w"))
        u += dur + rng.uniform(0.0, 0.4)

    got = assign_clusters(units, turns)
    ref = _brute_force(units, turns)
    overlapping = [
        k
        for k, (s, e, _txt) in enumerate(units)
        if any(min(e, te) - max(s, ts) > 0 for ts, te, _c in turns)
    ]
    # Exact agreement wherever a real overlap exists (the gap fallback is heuristic).
    for k in overlapping:
        assert got[k] == ref[k]


def test_assign_clusters_no_turns_and_gap_fallback():
    assert assign_clusters([(0.0, 1.0, "w")], []) == ["SPEAKER_00"]
    turns = [(0.0, 1.0, "A"), (10.0, 11.0, "B")]
    # Unit in the silence gap: nearest turn by midpoint wins.
    assert assign_clusters([(1.5, 2.0, "w")], turns) == ["A"]
    assert assign_clusters([(9.0, 9.5, "w")], turns) == ["B"]


def test_assign_clusters_handles_out_of_order_units():
    turns = [(0.0, 5.0, "A"), (5.0, 10.0, "B")]
    units = [(6.0, 7.0, "w"), (1.0, 2.0, "w")]  # second unit starts before the first
    assert assign_clusters(units, turns) == ["B", "A"]


# --- enqueue dedupe ---


def test_enqueue_dedupes_queued_and_running():
    async def run():
        proc = TranscriptionProcessor(whisper=None)  # type: ignore[arg-type]
        await proc.enqueue(7)
        await proc.enqueue(7)  # duplicate while queued — dropped
        assert proc._queue.qsize() == 1
        got = await proc._queue.get()
        proc._current_id = got
        proc._pending.discard(got)
        await proc.enqueue(7)  # duplicate while running — dropped
        assert proc._queue.qsize() == 0
        proc._current_id = None
        await proc.enqueue(7)  # job finished — a new enqueue is fine again
        assert proc._queue.qsize() == 1

    asyncio.run(run())


# --- delete guards ---


def test_delete_recording_blocked_while_processing(session):
    rec = Recording(status="processing")
    session.add(rec)
    session.commit()
    session.refresh(rec)
    with pytest.raises(HTTPException) as e:
        delete_recording(rec.id, session)
    assert e.value.status_code == 400
    assert session.get(Recording, rec.id) is not None


# --- enroll idempotency + withdrawal ---


def _speaker(session, rec_id, label, emb):
    from app.processing.diarize import VOICEPRINT_MODEL

    sp = Speaker(recording_id=rec_id, label=label, embedding=json.dumps(emb), embedding_model=VOICEPRINT_MODEL)
    session.add(sp)
    session.commit()
    session.refresh(sp)
    return sp


def test_repeat_rename_enrolls_once(session):
    rec = Recording(status="ready")
    session.add(rec)
    session.commit()
    session.refresh(rec)
    sp = _speaker(session, rec.id, "Speaker 1", [1.0, 0.0])
    rename_speaker(rec.id, sp.id, SpeakerRenameRequest(name="Alice"), session)
    rename_speaker(rec.id, sp.id, SpeakerRenameRequest(name="Alice"), session)
    alice = session.exec(select(Person).where(Person.name == "Alice")).one()
    assert alice.voiceprint_n == 1  # not double-counted


def test_corrected_rename_moves_sample_between_people(session):
    rec = Recording(status="ready")
    session.add(rec)
    session.commit()
    session.refresh(rec)
    sp = _speaker(session, rec.id, "Speaker 1", [1.0, 0.0])
    rename_speaker(rec.id, sp.id, SpeakerRenameRequest(name="Alice"), session)
    rename_speaker(rec.id, sp.id, SpeakerRenameRequest(name="Bob"), session)
    alice = session.exec(select(Person).where(Person.name == "Alice")).one()
    bob = session.exec(select(Person).where(Person.name == "Bob")).one()
    assert alice.voiceprint is None and alice.voiceprint_n == 0  # sample withdrawn
    assert json.loads(bob.voiceprint) == [1.0, 0.0] and bob.voiceprint_n == 1


def test_unlink_withdraws_sample(session):
    rec = Recording(status="ready")
    session.add(rec)
    session.commit()
    session.refresh(rec)
    sp = _speaker(session, rec.id, "Speaker 1", [1.0, 0.0])
    rename_speaker(rec.id, sp.id, SpeakerRenameRequest(name="Alice"), session)
    rename_speaker(rec.id, sp.id, SpeakerRenameRequest(name=""), session)  # revert
    alice = session.exec(select(Person).where(Person.name == "Alice")).one()
    assert alice.voiceprint is None and alice.voiceprint_n == 0


# --- compression path aliasing (mic-only recording: audio_path == mic_path) ---


def _write_wav(path):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x01" * 1600)


@pytest.mark.skipif(not compress.available(), reason="afconvert (macOS) not available")
def test_compress_handles_aliased_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "compress_audio", True)
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    mic = tmp_path / "mic.wav"
    _write_wav(mic)
    with Session(eng) as s:
        rec = Recording(status="processing", mic_path=str(mic), audio_path=str(mic))
        s.add(rec)
        s.commit()
        s.refresh(rec)
        rid = rec.id

    assert compress.compress_recording(rid, eng) is True
    with Session(eng) as s:
        rec = s.get(Recording, rid)
        # BOTH aliases now point at the single converted file; nothing dangles.
        assert rec.mic_path == rec.audio_path
        assert rec.mic_path.endswith(".m4a")
    assert not mic.exists()
    assert (tmp_path / "mic.m4a").exists()

    assert compress.restore_wavs(rid, eng) is True
    with Session(eng) as s:
        rec = s.get(Recording, rid)
        assert rec.mic_path == rec.audio_path
        assert rec.mic_path.endswith(".wav")
    assert mic.exists()
