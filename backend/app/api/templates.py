from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import PromptTemplate, SummaryTemplate

router = APIRouter(prefix="/api", tags=["templates"])


# ---------- summary templates (multi-section) ----------

class SummaryTemplateCreate(BaseModel):
    name: str
    sections: list[dict[str, Any]]


class SummaryTemplateUpdate(BaseModel):
    name: str | None = None
    sections: list[dict[str, Any]] | None = None


@router.get("/summary-templates", response_model=list[SummaryTemplate])
def list_summary_templates(session: Session = Depends(get_session)):
    return session.exec(select(SummaryTemplate).order_by(SummaryTemplate.id)).all()


@router.post("/summary-templates", response_model=SummaryTemplate)
def create_summary_template(payload: SummaryTemplateCreate, session: Session = Depends(get_session)):
    t = SummaryTemplate(name=payload.name, sections=payload.sections, builtin=False)
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


@router.put("/summary-templates/{template_id}", response_model=SummaryTemplate)
def update_summary_template(
    template_id: int, payload: SummaryTemplateUpdate, session: Session = Depends(get_session)
):
    t = session.get(SummaryTemplate, template_id)
    if not t:
        raise HTTPException(404)
    if payload.name is not None:
        t.name = payload.name
    if payload.sections is not None:
        t.sections = payload.sections
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


@router.delete("/summary-templates/{template_id}", status_code=204)
def delete_summary_template(template_id: int, session: Session = Depends(get_session)):
    t = session.get(SummaryTemplate, template_id)
    if not t:
        raise HTTPException(404)
    if t.builtin:
        raise HTTPException(400, "built-in templates cannot be deleted")
    session.delete(t)
    session.commit()


# ---------- Q&A prompt ----------

class QATemplateUpdate(BaseModel):
    body: str


@router.get("/qa-template", response_model=PromptTemplate | None)
def get_qa_template(session: Session = Depends(get_session)):
    return session.exec(select(PromptTemplate).order_by(PromptTemplate.id)).first()


@router.put("/qa-template", response_model=PromptTemplate)
def update_qa_template(payload: QATemplateUpdate, session: Session = Depends(get_session)):
    t = session.exec(select(PromptTemplate).order_by(PromptTemplate.id)).first()
    if t is None:
        raise HTTPException(404, "no qa template")
    t.body = payload.body
    session.add(t)
    session.commit()
    session.refresh(t)
    return t
