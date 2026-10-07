"""Trim keeps lines written during recording consistent with the trimmed audio."""
import json

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Recording, Segment, Speaker
from app.recording.recorder import shift_transcript


def test_shift_drops_outside_and_moves_inside():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        rec = Recording(status="processing", final_until_s=190.0)
        s.add(rec)
        s.commit()
        s.refresh(rec)
        keep = Speaker(recording_id=rec.id, label="You")
        gone = Speaker(recording_id=rec.id, label="Speaker 1")
        s.add(keep)
        s.add(gone)
        s.commit()
        s.add(Segment(recording_id=rec.id, speaker_id=gone.id, start_ts=30, end_ts=40, text="before trim"))
        s.add(Segment(recording_id=rec.id, speaker_id=keep.id, start_ts=150, end_ts=152, text="kept",
                      words=json.dumps([[150, 151, "kept"]])))
        s.add(Segment(recording_id=rec.id, speaker_id=keep.id, start_ts=200, end_ts=201, text="draft", is_draft=True))
        s.add(Segment(recording_id=rec.id, speaker_id=keep.id, start_ts=900, end_ts=901, text="after end"))
        s.commit()
        new_final = shift_transcript(s, rec.id, 120.0, 600.0, rec.final_until_s)
        s.commit()
        assert new_final == 70.0
        segs = s.exec(select(Segment).order_by(Segment.start_ts)).all()
        assert [(x.text, x.start_ts) for x in segs] == [("kept", 30.0), ("draft", 80.0)]
        assert json.loads(segs[0].words) == [[30, 31, "kept"]]
        assert [sp.label for sp in s.exec(select(Speaker)).all()] == ["You"]


def test_trim_before_any_final_window_returns_none():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        rec = Recording(status="processing", final_until_s=100.0)
        s.add(rec)
        s.commit()
        s.refresh(rec)
        assert shift_transcript(s, rec.id, 150.0, 400.0, rec.final_until_s) is None
