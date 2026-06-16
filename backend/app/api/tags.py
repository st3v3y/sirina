from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, delete, select

from ..db import get_session
from ..models import RecordingTag, Tag

router = APIRouter(prefix="/api/tags", tags=["tags"])


class TagCreate(BaseModel):
    name: str
    color: str | None = None


class TagUpdate(BaseModel):
    name: str | None = None
    color: str | None = None


@router.get("", response_model=list[Tag])
def list_tags(session: Session = Depends(get_session)):
    return session.exec(select(Tag).order_by(Tag.name)).all()


@router.post("", response_model=Tag)
def create_tag(payload: TagCreate, session: Session = Depends(get_session)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "name required")
    t = Tag(name=name, color=payload.color)
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


@router.put("/{tag_id}", response_model=Tag)
def update_tag(tag_id: int, payload: TagUpdate, session: Session = Depends(get_session)):
    t = session.get(Tag, tag_id)
    if not t:
        raise HTTPException(404)
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(400, "name required")
        t.name = name
    if payload.color is not None:
        t.color = payload.color
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


@router.delete("/{tag_id}", status_code=204)
def delete_tag(tag_id: int, session: Session = Depends(get_session)):
    t = session.get(Tag, tag_id)
    if not t:
        raise HTTPException(404)
    # Cascade: remove the m2m links; recordings are untouched.
    session.exec(delete(RecordingTag).where(RecordingTag.tag_id == tag_id))  # type: ignore[arg-type]
    session.delete(t)
    session.commit()
