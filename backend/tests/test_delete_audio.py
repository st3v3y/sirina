"""Delete-audio-only: removes the on-disk tracks and clears paths, but keeps the
transcript, summary and speakers; blocked while recording/processing."""
import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from app.api.recordings import delete_recording_audio, reprocess_recording
from app.config import settings
from app.models import Recording, Segment, Speaker, Summary


@pytest.fixture
def session(tmp_path, monkeypatch):
    # Point the recordings dir at tmp so the endpoint's directory cleanup is exercised.
    monkeypatch.setattr(settings, "app_data_dir", str(tmp_path))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _recording_with_audio(session, tmp_path, status="ready"):
    rec_dir = tmp_path / "recordings" / "1"
    rec_dir.mkdir(parents=True)
    paths = {}
    for name in ("mic", "system", "mixed"):
        p = rec_dir / f"{name}.wav"
        p.write_bytes(b"RIFF")
        paths[name] = p
    rec = Recording(
        status=status,
        mic_path=str(paths["mic"]),
        system_path=str(paths["system"]),
        audio_path=str(paths["mixed"]),
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    sp = Speaker(recording_id=rec.id, label="You")
    session.add(sp)
    session.flush()
    session.add(Segment(recording_id=rec.id, speaker_id=sp.id, start_ts=0, end_ts=1, text="hi"))
    session.add(Summary(recording_id=rec.id, sections=[{"title": "t", "content": "c"}]))
    session.commit()
    return rec, rec_dir


def test_delete_audio_removes_files_keeps_transcript(session, tmp_path):
    rec, rec_dir = _recording_with_audio(session, tmp_path)
    delete_recording_audio(rec.id, session)
    assert not rec_dir.exists()
    session.refresh(rec)
    assert rec.mic_path is None and rec.system_path is None and rec.audio_path is None
    assert rec.status == "ready"
    # transcript + summary survive
    assert session.exec(select(Segment).where(Segment.recording_id == rec.id)).all()
    assert session.exec(select(Summary).where(Summary.recording_id == rec.id)).all()
    assert session.exec(select(Speaker).where(Speaker.recording_id == rec.id)).all()


def test_delete_audio_blocked_while_processing(session, tmp_path):
    rec, rec_dir = _recording_with_audio(session, tmp_path, status="processing")
    with pytest.raises(HTTPException) as e:
        delete_recording_audio(rec.id, session)
    assert e.value.status_code == 400
    assert rec_dir.exists()


def test_reprocess_blocked_after_audio_deleted(session, tmp_path):
    import asyncio

    rec, _ = _recording_with_audio(session, tmp_path)
    delete_recording_audio(rec.id, session)
    with pytest.raises(HTTPException) as e:
        asyncio.run(reprocess_recording(rec.id, session))
    assert e.value.status_code == 400
    assert "audio was deleted" in e.value.detail
