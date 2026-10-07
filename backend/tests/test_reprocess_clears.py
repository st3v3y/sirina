"""Reprocess rebuilds from scratch: old final/draft lines, speakers and the boundary go."""
import asyncio

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.api import recordings as rec_api
from app.models import Recording, Segment, Speaker


class FakeProcessor:
    def __init__(self):
        self.enqueued = []

    def current_id(self):
        return None

    async def enqueue(self, rid):
        self.enqueued.append(rid)


def test_reprocess_clears_transcript_and_boundary(tmp_path, monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        rec = Recording(status="ready", audio_path=str(tmp_path / "a.wav"), final_until_s=120.0)
        s.add(rec)
        s.commit()
        s.refresh(rec)
        sp = Speaker(recording_id=rec.id, label="You")
        s.add(sp)
        s.commit()
        s.refresh(sp)
        s.add(Segment(recording_id=rec.id, speaker_id=sp.id, start_ts=0, end_ts=1, text="final"))
        s.add(Segment(recording_id=rec.id, speaker_id=sp.id, start_ts=130, end_ts=131, text="draft", is_draft=True))
        s.commit()
        rid = rec.id
    proc = FakeProcessor()
    monkeypatch.setattr(rec_api.runtime, "processor", proc)
    with Session(eng) as s:
        asyncio.run(rec_api.reprocess_recording(rid, session=s))
    with Session(eng) as s:
        assert s.exec(select(Segment)).all() == []
        assert s.exec(select(Speaker)).all() == []
        rec = s.get(Recording, rid)
        assert rec.final_until_s is None and rec.status == "processing"
    assert proc.enqueued == [rid]
