from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Person, Recording, Speaker

router = APIRouter(prefix="/api/people", tags=["people"])


class PersonOut(BaseModel):
    id: int
    name: str
    recording_count: int
    last_recording_at: datetime | None


class PersonUpdate(BaseModel):
    name: str


@router.get("", response_model=list[PersonOut])
def list_people(session: Session = Depends(get_session)) -> list[PersonOut]:
    people = session.exec(select(Person).order_by(Person.name)).all()
    out: list[PersonOut] = []
    for p in people:
        # recordings this person appears in (distinct via their speakers)
        rec_ids = set(
            session.exec(select(Speaker.recording_id).where(Speaker.person_id == p.id)).all()  # type: ignore[arg-type]
        )
        last: datetime | None = None
        if rec_ids:
            starts = session.exec(
                select(Recording.started_at).where(Recording.id.in_(rec_ids))  # type: ignore[attr-defined]
            ).all()
            last = max(starts) if starts else None
        out.append(
            PersonOut(id=p.id, name=p.name, recording_count=len(rec_ids), last_recording_at=last)  # type: ignore[arg-type]
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
    p.name = name
    session.add(p)
    session.commit()
    session.refresh(p)
    rec_ids = set(session.exec(select(Speaker.recording_id).where(Speaker.person_id == p.id)).all())  # type: ignore[arg-type]
    return PersonOut(id=p.id, name=p.name, recording_count=len(rec_ids), last_recording_at=None)  # type: ignore[arg-type]


@router.delete("/{person_id}", status_code=204)
def delete_person(person_id: int, session: Session = Depends(get_session)) -> None:
    p = session.get(Person, person_id)
    if not p:
        raise HTTPException(404)
    # Unlink speakers (revert to their default label); keep recordings/transcripts.
    speakers = session.exec(select(Speaker).where(Speaker.person_id == person_id)).all()
    for sp in speakers:
        sp.person_id = None
        session.add(sp)
    session.delete(p)
    session.commit()
