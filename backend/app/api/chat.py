"""Cross-recording AI chat: sessions whose questions are answered over all
transcripts (see Pipeline.cross_ask)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, delete, select

from ..db import get_session
from ..llm.provider import LLMError
from ..models import ChatMessage, ChatSession
from ..runtime import runtime

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessageOut(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    created_at: datetime


class ChatSessionOut(BaseModel):
    id: int
    title: str | None
    created_at: datetime
    messages: list[ChatMessageOut]


class SessionCreate(BaseModel):
    title: str | None = None


class AskRequest(BaseModel):
    question: str


def _session_out(session: Session, sess: ChatSession) -> ChatSessionOut:
    msgs = session.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == sess.id)
        .order_by(ChatMessage.created_at)
    ).all()
    return ChatSessionOut(
        id=sess.id,  # type: ignore[arg-type]
        title=sess.title,
        created_at=sess.created_at,
        messages=[ChatMessageOut(**m.model_dump()) for m in msgs],
    )


@router.get("/sessions", response_model=list[ChatSessionOut])
def list_sessions(session: Session = Depends(get_session)) -> list[ChatSessionOut]:
    sessions = session.exec(
        select(ChatSession).order_by(ChatSession.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [_session_out(session, s) for s in sessions]


@router.post("/sessions", response_model=ChatSessionOut)
def create_session(payload: SessionCreate, session: Session = Depends(get_session)) -> ChatSessionOut:
    sess = ChatSession(title=(payload.title or "").strip() or None)
    session.add(sess)
    session.commit()
    session.refresh(sess)
    return _session_out(session, sess)


@router.post("/sessions/{session_id}/ask")
async def ask_session(session_id: int, payload: AskRequest) -> dict[str, str]:
    if runtime.pipeline is None:
        raise HTTPException(503, "pipeline not running")
    question = payload.question.strip()
    if not question:
        raise HTTPException(400, "question required")
    try:
        answer = await runtime.pipeline.cross_ask(session_id=session_id, question=question)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    except LLMError as e:
        raise HTTPException(502, str(e)) from e
    return {"answer": answer}


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: int, session: Session = Depends(get_session)) -> None:
    sess = session.get(ChatSession, session_id)
    if not sess:
        raise HTTPException(404)
    session.exec(delete(ChatMessage).where(ChatMessage.session_id == session_id))  # type: ignore[arg-type]
    session.delete(sess)
    session.commit()
