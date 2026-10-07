"""Voice fingerprints: enrollment (running mean), cross-recording auto-matching,
and the manual-rename → enroll path."""
import json

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app import voiceprints
from app.api.recordings import SpeakerRenameRequest, rename_speaker
from app.config import settings
from app.models import Person, Recording, Speaker
from app.processing.diarize import VOICEPRINT_MODEL
from app.voiceprints import cosine_similarity, enroll, match_speakers


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _recording(session, **kw) -> Recording:
    rec = Recording(status="ready", **kw)
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def _speaker(session, rec, label, embedding=None, person_id=None, model=VOICEPRINT_MODEL) -> Speaker:
    sp = Speaker(
        recording_id=rec.id,
        label=label,
        embedding=json.dumps(embedding) if embedding is not None else None,
        embedding_model=model if embedding is not None else None,
        person_id=person_id,
    )
    session.add(sp)
    session.commit()
    session.refresh(sp)
    return sp


def _person(session, name, voiceprint=None, n=0, is_self=False, model=VOICEPRINT_MODEL) -> Person:
    p = Person(
        name=name,
        voiceprint=json.dumps(voiceprint) if voiceprint is not None else None,
        voiceprint_n=n,
        voiceprint_model=model if voiceprint is not None else None,
        is_self=is_self,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


# --- enrollment ---


def test_enroll_first_sample_sets_voiceprint():
    p = Person(name="Alice")
    enroll(p, [1.0, 0.0])
    assert json.loads(p.voiceprint) == [1.0, 0.0]
    assert p.voiceprint_n == 1


def test_enroll_running_mean():
    p = Person(name="Alice")
    enroll(p, [1.0, 0.0])
    enroll(p, [0.0, 1.0])
    assert json.loads(p.voiceprint) == [0.5, 0.5]
    assert p.voiceprint_n == 2


def test_enroll_model_change_restarts():
    # Same size, different embedding space (pyannote → SpeakerKit): never mixed.
    p = Person(name="Alice", voiceprint=json.dumps([1.0, 0.0]), voiceprint_n=3, voiceprint_model="old")
    enroll(p, [0.0, 1.0])
    assert json.loads(p.voiceprint) == [0.0, 1.0] and p.voiceprint_n == 1
    assert p.voiceprint_model == VOICEPRINT_MODEL


def test_untagged_fingerprints_never_match(session, monkeypatch):
    monkeypatch.setattr(settings, "voice_match_threshold", 0.5)
    _person(session, "Old", voiceprint=[1.0, 0.0], n=2, model=None)
    rec = _recording(session)
    _speaker(session, rec, "Speaker 1", embedding=[1.0, 0.0])
    assert match_speakers(session, rec.id) == []


def test_enroll_dimension_change_restarts():
    # A diarization-model change alters the embedding dimension; the stale
    # voiceprint is discarded rather than mixed with incompatible vectors.
    p = Person(name="Alice", voiceprint=json.dumps([1.0, 0.0]), voiceprint_n=3)
    enroll(p, [0.0, 1.0, 0.0])
    assert json.loads(p.voiceprint) == [0.0, 1.0, 0.0]
    assert p.voiceprint_n == 1


# --- matching ---


def test_match_links_similar_speaker(session, monkeypatch):
    monkeypatch.setattr(settings, "voice_match_threshold", 0.5)
    alice = _person(session, "Alice", voiceprint=[1.0, 0.0])
    rec = _recording(session)
    sp = _speaker(session, rec, "Speaker 1", embedding=[0.9, 0.1])
    linked = match_speakers(session, rec.id)
    assert linked == [(sp.id, alice.id)]
    assert session.get(Speaker, sp.id).person_id == alice.id


def test_match_below_threshold_links_nothing(session, monkeypatch):
    monkeypatch.setattr(settings, "voice_match_threshold", 0.5)
    _person(session, "Alice", voiceprint=[1.0, 0.0])
    rec = _recording(session)
    sp = _speaker(session, rec, "Speaker 1", embedding=[0.0, 1.0])  # orthogonal
    assert match_speakers(session, rec.id) == []
    assert session.get(Speaker, sp.id).person_id is None


def test_match_never_creates_people_and_skips_self(session, monkeypatch):
    monkeypatch.setattr(settings, "voice_match_threshold", 0.5)
    _person(session, "Me", voiceprint=[1.0, 0.0], is_self=True)
    rec = _recording(session)
    _speaker(session, rec, "Speaker 1", embedding=[1.0, 0.0])
    assert match_speakers(session, rec.id) == []
    assert len(session.exec(select(Person)).all()) == 1


def test_match_is_one_to_one_best_first(session, monkeypatch):
    # Two speakers both resemble Alice; only the closer one links to her, and the
    # other takes the next-best person instead of double-booking Alice.
    monkeypatch.setattr(settings, "voice_match_threshold", 0.5)
    alice = _person(session, "Alice", voiceprint=[1.0, 0.0])
    bob = _person(session, "Bob", voiceprint=[0.7, 0.7])
    rec = _recording(session)
    sp1 = _speaker(session, rec, "Speaker 1", embedding=[1.0, 0.05])  # very Alice
    sp2 = _speaker(session, rec, "Speaker 2", embedding=[0.9, 0.5])  # Alice-ish, Bob-ish
    match_speakers(session, rec.id)
    assert session.get(Speaker, sp1.id).person_id == alice.id
    assert session.get(Speaker, sp2.id).person_id == bob.id


def test_match_disabled_by_zero_threshold(session, monkeypatch):
    monkeypatch.setattr(settings, "voice_match_threshold", 0.0)
    _person(session, "Alice", voiceprint=[1.0, 0.0])
    rec = _recording(session)
    _speaker(session, rec, "Speaker 1", embedding=[1.0, 0.0])
    assert match_speakers(session, rec.id) == []


def test_match_ignores_already_linked_speakers(session, monkeypatch):
    monkeypatch.setattr(settings, "voice_match_threshold", 0.5)
    alice = _person(session, "Alice", voiceprint=[1.0, 0.0])
    carol = _person(session, "Carol")
    rec = _recording(session)
    sp = _speaker(session, rec, "Speaker 1", embedding=[1.0, 0.0], person_id=carol.id)
    assert match_speakers(session, rec.id) == []
    assert session.get(Speaker, sp.id).person_id == carol.id
    assert alice.id is not None


# --- manual rename enrolls ---


def test_rename_enrolls_embedding_into_person(session):
    rec = _recording(session)
    sp = _speaker(session, rec, "Speaker 1", embedding=[0.6, 0.8])
    out = rename_speaker(rec.id, sp.id, SpeakerRenameRequest(name="Alice"), session)
    person = session.get(Person, out.person_id)
    assert json.loads(person.voiceprint) == [0.6, 0.8]
    assert person.voiceprint_n == 1


def test_rename_without_embedding_leaves_voiceprint_empty(session):
    rec = _recording(session)
    sp = _speaker(session, rec, "Speaker 1")
    out = rename_speaker(rec.id, sp.id, SpeakerRenameRequest(name="Alice"), session)
    person = session.get(Person, out.person_id)
    assert person.voiceprint is None


def test_rename_second_speaker_merges_voiceprint(session):
    rec = _recording(session)
    sp1 = _speaker(session, rec, "Speaker 1", embedding=[1.0, 0.0])
    rename_speaker(rec.id, sp1.id, SpeakerRenameRequest(name="Alice"), session)
    rec2 = _recording(session)
    sp2 = _speaker(session, rec2, "Speaker 1", embedding=[0.0, 1.0])
    out = rename_speaker(rec2.id, sp2.id, SpeakerRenameRequest(name="Alice"), session)
    person = session.get(Person, out.person_id)
    assert json.loads(person.voiceprint) == [0.5, 0.5]
    assert person.voiceprint_n == 2


def test_cosine_similarity_basics():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([], []) == 0.0
    assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0
    assert voiceprints.decode("not json") is None
    assert voiceprints.decode(None) is None
    assert voiceprints.decode(json.dumps([1, 2])) == [1.0, 2.0]
