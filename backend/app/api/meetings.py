from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, delete, select

from ..db import get_session
from ..exporters import export_markdown, export_text
from ..models import Meeting, QAMessage, Segment, Summary
from ..runtime import runtime

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


class StartRequest(BaseModel):
    source: str = "discord"  # "discord" | "local"
    channel_id: str | None = None
    title: str | None = None
    device: str | None = None       # name or numeric index, used when source == "local"
    label: str | None = None        # display name for the local "speaker", default "Room"


class StopRequest(BaseModel):
    summary_template_id: int | None = None


class MeetingListItem(BaseModel):
    id: int
    title: str | None
    guild_id: str
    channel_id: str
    started_at: datetime
    ended_at: datetime | None
    status: str
    source: str
    segment_count: int


class MeetingDetailResponse(BaseModel):
    id: int
    title: str | None
    guild_id: str
    channel_id: str
    started_at: datetime
    ended_at: datetime | None
    status: str
    source: str
    segments: list[Segment]
    summaries: list[Summary]
    qa: list[QAMessage]


@router.post("/start")
async def start_meeting(payload: StartRequest) -> dict[str, int]:
    if runtime.pipeline is None:
        raise HTTPException(503, "pipeline not running")

    source = (payload.source or "discord").lower()
    if source == "local":
        device: str | int | None = None
        if payload.device:
            try:
                device = int(payload.device)
            except ValueError:
                device = payload.device
        try:
            meeting_id = await runtime.pipeline.start_local_meeting(
                device=device,
                label=payload.label,
                title=payload.title,
            )
        except Exception as e:
            raise HTTPException(400, f"could not start local recording: {e}") from e
        return {"meeting_id": meeting_id}

    # discord (default)
    if runtime.bot is None:
        raise HTTPException(503, "Discord bot not configured (set DISCORD_TOKEN)")
    if not runtime.bot.is_ready():
        raise HTTPException(503, "Discord bot not ready")
    meeting_id = await runtime.pipeline.start_meeting(
        channel_id=int(payload.channel_id) if payload.channel_id else None,
        title=payload.title,
    )
    return {"meeting_id": meeting_id}


@router.post("/{meeting_id}/stop")
async def stop_meeting(meeting_id: int, payload: StopRequest) -> dict[str, bool]:
    if runtime.pipeline is None:
        raise HTTPException(503, "pipeline not running")
    await runtime.pipeline.stop_meeting(
        meeting_id=meeting_id,
        summary_template_id=payload.summary_template_id,
    )
    return {"ok": True}


@router.get("", response_model=list[MeetingListItem])
def list_meetings(session: Session = Depends(get_session)) -> list[MeetingListItem]:
    meetings = session.exec(select(Meeting).order_by(Meeting.started_at.desc())).all()  # type: ignore[attr-defined]
    out: list[MeetingListItem] = []
    for m in meetings:
        count = session.exec(
            select(Segment.id).where(Segment.meeting_id == m.id)  # type: ignore[arg-type]
        ).all()
        out.append(
            MeetingListItem(
                id=m.id,  # type: ignore[arg-type]
                title=m.title,
                guild_id=m.guild_id,
                channel_id=m.channel_id,
                started_at=m.started_at,
                ended_at=m.ended_at,
                status=m.status,
                source=m.source,
                segment_count=len(count),
            )
        )
    return out


@router.get("/{meeting_id}", response_model=MeetingDetailResponse)
def get_meeting(meeting_id: int, session: Session = Depends(get_session)) -> MeetingDetailResponse:
    m = session.get(Meeting, meeting_id)
    if not m:
        raise HTTPException(404)
    segments = session.exec(
        select(Segment).where(Segment.meeting_id == meeting_id).order_by(Segment.start_ts)  # type: ignore[arg-type]
    ).all()
    summaries = session.exec(
        select(Summary).where(Summary.meeting_id == meeting_id).order_by(Summary.created_at)  # type: ignore[arg-type]
    ).all()
    qa = session.exec(
        select(QAMessage).where(QAMessage.meeting_id == meeting_id).order_by(QAMessage.created_at)  # type: ignore[arg-type]
    ).all()
    return MeetingDetailResponse(
        id=m.id,  # type: ignore[arg-type]
        title=m.title,
        guild_id=m.guild_id,
        channel_id=m.channel_id,
        started_at=m.started_at,
        ended_at=m.ended_at,
        status=m.status,
        source=m.source,
        segments=list(segments),
        summaries=list(summaries),
        qa=list(qa),
    )


@router.delete("/{meeting_id}", status_code=204)
def delete_meeting(meeting_id: int, session: Session = Depends(get_session)) -> None:
    m = session.get(Meeting, meeting_id)
    if not m:
        raise HTTPException(404)
    if m.status == "recording":
        raise HTTPException(400, "stop the meeting before deleting")
    session.exec(delete(Segment).where(Segment.meeting_id == meeting_id))  # type: ignore[arg-type]
    session.exec(delete(Summary).where(Summary.meeting_id == meeting_id))  # type: ignore[arg-type]
    session.exec(delete(QAMessage).where(QAMessage.meeting_id == meeting_id))  # type: ignore[arg-type]
    session.delete(m)
    session.commit()


class SummarizeRequest(BaseModel):
    template_id: int


@router.post("/{meeting_id}/summarize")
async def summarize_meeting(meeting_id: int, payload: SummarizeRequest) -> dict[str, str | int]:
    if runtime.pipeline is None:
        raise HTTPException(503, "pipeline not running")
    s = await runtime.pipeline.summarize(meeting_id=meeting_id, template_id=payload.template_id)
    return {"summary_id": s.id or 0, "content": s.content}


class AskRequest(BaseModel):
    question: str
    template_id: int | None = None


@router.post("/{meeting_id}/ask")
async def ask_meeting(meeting_id: int, payload: AskRequest) -> dict[str, str]:
    if runtime.pipeline is None:
        raise HTTPException(503, "pipeline not running")
    answer = await runtime.pipeline.ask(
        meeting_id=meeting_id, question=payload.question, template_id=payload.template_id
    )
    return {"answer": answer}


@router.get("/{meeting_id}/export")
def export_meeting(meeting_id: int, format: str = "md") -> Response:
    if format not in {"md", "txt"}:
        raise HTTPException(400, "format must be md or txt")
    body = export_markdown(meeting_id) if format == "md" else export_text(meeting_id)
    media_type = "text/markdown" if format == "md" else "text/plain"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=meeting-{meeting_id}.{format}"},
    )
