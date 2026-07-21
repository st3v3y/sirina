from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from ..db import get_session
from ..models import Person, Recording, Speaker

router = APIRouter(prefix="/api/people", tags=["people"])


class PersonOut(BaseModel):
    id: int
    name: str
    recording_count: int
    last_recording_at: datetime | None
    is_self: bool = False
    # True once a voice fingerprint is enrolled (by renaming a diarized speaker to this
    # person) — future recordings will auto-recognise them.
    has_voiceprint: bool = False


class PersonUpdate(BaseModel):
    name: str


@router.get("", response_model=list[PersonOut])
def list_people(session: Session = Depends(get_session)) -> list[PersonOut]:
    people = session.exec(select(Person).order_by(Person.name)).all()
    # One grouped query for everyone's meeting count + latest meeting (was 2 queries
    # per person — N+1 on the People page).
    stats: dict[int, tuple[int, datetime | None]] = {
        person_id: (count, last)
        for person_id, count, last in session.exec(
            select(
                Speaker.person_id,
                func.count(func.distinct(Speaker.recording_id)),
                func.max(Recording.started_at),
            )
            .join(Recording, Recording.id == Speaker.recording_id)  # type: ignore[arg-type]
            .where(Speaker.person_id != None)  # noqa: E711
            .group_by(Speaker.person_id)  # type: ignore[arg-type]
        ).all()
    }
    out: list[PersonOut] = []
    for p in people:
        count, last = stats.get(p.id, (0, None))  # type: ignore[arg-type]
        out.append(
            PersonOut(
                id=p.id, name=p.name, recording_count=count,  # type: ignore[arg-type]
                last_recording_at=last, is_self=bool(p.is_self),
                has_voiceprint=bool(p.voiceprint),
            )
        )
    return out


@router.put("/{person_id}", response_model=PersonOut)
def rename_person(person_id: int, payload: PersonUpdate, session: Session = Depends(get_session)) -> PersonOut:
    p = session.get(Person, person_id)
    if not p:
        raise HTTPException(404)
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "name required")
    clash = session.exec(
        select(Person).where(func.lower(Person.name) == name.lower(), Person.id != person_id)
    ).first()
    if clash is not None:
        raise HTTPException(400, f"a person named '{clash.name}' already exists")
    p.name = name
    session.add(p)
    session.commit()
    session.refresh(p)
    rec_ids = set(session.exec(select(Speaker.recording_id).where(Speaker.person_id == p.id)).all())  # type: ignore[arg-type]
    return PersonOut(id=p.id, name=p.name, recording_count=len(rec_ids), last_recording_at=None, is_self=bool(p.is_self), has_voiceprint=bool(p.voiceprint))  # type: ignore[arg-type]


@router.delete("/{person_id}", status_code=204)
def delete_person(person_id: int, session: Session = Depends(get_session)) -> None:
    p = session.get(Person, person_id)
    if not p:
        raise HTTPException(404)
    # Unlink speakers (revert to their default label); keep recordings/transcripts.
    # Their voiceprint enrollments died with the person, so clear the flags too.
    speakers = session.exec(select(Speaker).where(Speaker.person_id == person_id)).all()
    for sp in speakers:
        sp.person_id = None
        sp.enrolled = False
        session.add(sp)
    session.delete(p)
    session.commit()
