"""Drafts never reach summaries/exports; Q&A sees them, labelled."""
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.exporters as exporters
from app.models import Recording, Segment, Speaker
from app.pipeline import Pipeline


def _db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        rec = Recording(status="processing", title="T")
        s.add(rec)
        s.commit()
        s.refresh(rec)
        sp = Speaker(recording_id=rec.id, label="You")
        s.add(sp)
        s.commit()
        s.refresh(sp)
        s.add(Segment(recording_id=rec.id, speaker_id=sp.id, start_ts=0, end_ts=1, text="final words"))
        s.add(Segment(recording_id=rec.id, speaker_id=sp.id, start_ts=5, end_ts=6, text="rough words", is_draft=True))
        s.commit()
        return eng, rec.id


def test_summary_transcript_is_final_only():
    eng, rid = _db()
    with Session(eng) as s:
        text = Pipeline(None, None)._transcript(s, rid)
    assert "final words" in text and "rough words" not in text


def test_qa_transcript_labels_drafts():
    eng, rid = _db()
    with Session(eng) as s:
        text = Pipeline(None, None)._transcript(s, rid, include_drafts=True)
    assert "[draft] rough words" in text and "still being finalized" in text


def test_export_is_final_only(monkeypatch):
    eng, rid = _db()
    monkeypatch.setattr(exporters, "engine", eng)
    md = exporters.export_markdown(rid)
    assert "final words" in md and "rough words" not in md
