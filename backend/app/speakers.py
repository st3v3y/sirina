"""Helpers for resolving a recording's speakers to display names."""
from __future__ import annotations

from sqlmodel import Session, select

from .models import Person, Speaker


SELF_LABEL = "You"


def get_or_create_self_person(session: Session) -> Person:
    """The singleton Person representing the app user (the mic / "You" speaker). Created
    on first use with the default name "You"; reused across all recordings so renaming it
    once applies everywhere."""
    p = session.exec(select(Person).where(Person.is_self == True)).first()  # noqa: E712
    if p is None:
        p = Person(name=SELF_LABEL, is_self=True)
        session.add(p)
        session.flush()  # assign id
    return p


def display_name(speaker: Speaker, persons: dict[int, str]) -> str:
    if speaker.person_id is not None:
        return persons.get(speaker.person_id, speaker.label)
    return speaker.label


def speaker_names(session: Session, recording_id: int) -> dict[int, str]:
    """Map speaker_id -> display name (linked Person's name, else the label)."""
    speakers = session.exec(
        select(Speaker).where(Speaker.recording_id == recording_id)
    ).all()
    persons = {p.id: p.name for p in session.exec(select(Person)).all() if p.id is not None}
    return {sp.id: display_name(sp, persons) for sp in speakers if sp.id is not None}
