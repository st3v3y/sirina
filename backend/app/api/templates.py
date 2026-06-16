from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import PromptTemplate

router = APIRouter(prefix="/api/templates", tags=["templates"])


class TemplateCreate(BaseModel):
    name: str
    kind: str
    body: str


class TemplateUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None
    body: str | None = None


@router.get("", response_model=list[PromptTemplate])
def list_templates(session: Session = Depends(get_session)):
    return session.exec(select(PromptTemplate).order_by(PromptTemplate.kind, PromptTemplate.id)).all()


@router.post("", response_model=PromptTemplate)
def create_template(payload: TemplateCreate, session: Session = Depends(get_session)):
    if payload.kind not in {"summary", "aspects", "qa"}:
        raise HTTPException(400, "kind must be summary|aspects|qa")
    t = PromptTemplate(name=payload.name, kind=payload.kind, body=payload.body)
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


@router.put("/{template_id}", response_model=PromptTemplate)
def update_template(template_id: int, payload: TemplateUpdate, session: Session = Depends(get_session)):
    t = session.get(PromptTemplate, template_id)
    if not t:
        raise HTTPException(404)
    if payload.name is not None:
        t.name = payload.name
    if payload.kind is not None:
        if payload.kind not in {"summary", "aspects", "qa"}:
            raise HTTPException(400, "kind must be summary|aspects|qa")
        t.kind = payload.kind
    if payload.body is not None:
        t.body = payload.body
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: int, session: Session = Depends(get_session)):
    t = session.get(PromptTemplate, template_id)
    if not t:
        raise HTTPException(404)
    if t.is_default:
        raise HTTPException(400, "default templates cannot be deleted")
    session.delete(t)
    session.commit()
