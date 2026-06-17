"""Regression tests for speaker rename: find-or-create Person, case-insensitive
reuse, and the guard that default/unchanged labels never create junk People."""
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.api.recordings import SpeakerRenameRequest, rename_speaker
from app.models import Person, Recording, Speaker


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        rec = Recording(status="ready")
        s.add(rec)
        s.commit()
        s.refresh(rec)
        sp1 = Speaker(recording_id=rec.id, label="Speaker 1")
        sp2 = Speaker(recording_id=rec.id, label="Speaker 2")
        s.add(sp1)
        s.add(sp2)
        s.commit()
        s.refresh(sp1)
        s.refresh(sp2)
        s._rec_id = rec.id  # type: ignore[attr-defined]
        s._sp1 = sp1.id  # type: ignore[attr-defined]
        s._sp2 = sp2.id  # type: ignore[attr-defined]
        yield s


def _people(session):
    return session.exec(select(Person)).all()


def test_rename_creates_person(session):
    out = rename_speaker(session._rec_id, session._sp1, SpeakerRenameRequest(name="Alice"), session)
    assert out.name == "Alice"
    assert out.person_id is not None
    assert {p.name for p in _people(session)} == {"Alice"}


def test_case_insensitive_reuse_no_duplicate(session):
    rename_speaker(session._rec_id, session._sp1, SpeakerRenameRequest(name="Alice"), session)
    out2 = rename_speaker(session._rec_id, session._sp2, SpeakerRenameRequest(name="alice"), session)
    # Both speakers point at the same single Person; no duplicate created.
    assert len(_people(session)) == 1
    sp1 = session.get(Speaker, session._sp1)
    assert out2.person_id == sp1.person_id


def test_default_label_creates_no_person(session):
    # Submitting the speaker's own default label must be a no-op (junk-People bug).
    out = rename_speaker(session._rec_id, session._sp1, SpeakerRenameRequest(name="Speaker 1"), session)
    assert out.person_id is None
    assert _people(session) == []


def test_empty_name_unlinks(session):
    rename_speaker(session._rec_id, session._sp1, SpeakerRenameRequest(name="Alice"), session)
    out = rename_speaker(session._rec_id, session._sp1, SpeakerRenameRequest(name="  "), session)
    assert out.person_id is None
    assert out.name == "Speaker 1"  # reverts to default label
