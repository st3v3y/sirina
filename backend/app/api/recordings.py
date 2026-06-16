from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, delete, select

from ..config import settings
from ..db import get_session
from ..exporters import export_markdown, export_text
from ..models import QAMessage, Recording, Segment, Summary
from ..runtime import runtime

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recordings", tags=["recordings"])


class StartRequest(BaseModel):
    title: str | None = None
    device: str | None = None         # primary (mic) input device name or index
    system_device: str | None = None  # optional system-audio device (e.g. BlackHole)
    label: str | None = None          # display label, default "Room"


class RecordingListItem(BaseModel):
    id: int
    title: str | None
    started_at: datetime
    ended_at: datetime | None
    duration_s: float | None
    status: str
    segment_count: int


class RecordingDetail(BaseModel):
    id: int
    title: str | None
    started_at: datetime
    ended_at: datetime | None
    duration_s: float | None
    status: str
    language: str | None
    segments: list[Segment]
    summaries: list[Summary]
    qa: list[QAMessage]


class ActiveInfo(BaseModel):
    id: int
    elapsed_s: float
    level: float


@router.post("/start")
async def start_recording(payload: StartRequest) -> dict[str, int]:
    if runtime.recorder is None:
        raise HTTPException(503, "recorder not running")

    def _coerce(v: str | None) -> str | int | None:
        if not v:
            return None
        try:
            return int(v)
        except ValueError:
            return v

    try:
        recording_id = await runtime.recorder.start(
            device=_coerce(payload.device),
            system_device=_coerce(payload.system_device),
            label=payload.label,
            title=payload.title,
        )
    except Exception as e:
        raise HTTPException(400, f"could not start recording: {e}") from e
    return {"id": recording_id}


@router.post("/{recording_id}/stop")
async def stop_recording(recording_id: int) -> dict[str, bool]:
    if runtime.recorder is None:
        raise HTTPException(503, "recorder not running")
    await runtime.recorder.stop(recording_id)
    # Hand off to the background transcription processor (recording is now `processing`).
    if runtime.processor is not None:
        await runtime.processor.enqueue(recording_id)
    return {"ok": True}


@router.get("/active", response_model=ActiveInfo | None)
async def active_recording() -> ActiveInfo | None:
    if runtime.recorder is None:
        return None
    info = runtime.recorder.active_info()
    return ActiveInfo(**info) if info else None


@router.get("", response_model=list[RecordingListItem])
def list_recordings(session: Session = Depends(get_session)) -> list[RecordingListItem]:
    recs = session.exec(select(Recording).order_by(Recording.started_at.desc())).all()  # type: ignore[attr-defined]
    out: list[RecordingListItem] = []
    for r in recs:
        count = session.exec(select(Segment.id).where(Segment.recording_id == r.id)).all()  # type: ignore[arg-type]
        out.append(
            RecordingListItem(
                id=r.id,  # type: ignore[arg-type]
                title=r.title,
                started_at=r.started_at,
                ended_at=r.ended_at,
                duration_s=r.duration_s,
                status=r.status,
                segment_count=len(count),
            )
        )
    return out


@router.get("/{recording_id}", response_model=RecordingDetail)
def get_recording(recording_id: int, session: Session = Depends(get_session)) -> RecordingDetail:
    r = session.get(Recording, recording_id)
    if not r:
        raise HTTPException(404)
    segments = session.exec(
        select(Segment).where(Segment.recording_id == recording_id).order_by(Segment.start_ts)  # type: ignore[arg-type]
    ).all()
    summaries = session.exec(
        select(Summary).where(Summary.recording_id == recording_id).order_by(Summary.created_at)  # type: ignore[arg-type]
    ).all()
    qa = session.exec(
        select(QAMessage).where(QAMessage.recording_id == recording_id).order_by(QAMessage.created_at)  # type: ignore[arg-type]
    ).all()
    return RecordingDetail(
        id=r.id,  # type: ignore[arg-type]
        title=r.title,
        started_at=r.started_at,
        ended_at=r.ended_at,
        duration_s=r.duration_s,
        status=r.status,
        language=r.language,
        segments=list(segments),
        summaries=list(summaries),
        qa=list(qa),
    )


@router.delete("/{recording_id}", status_code=204)
def delete_recording(recording_id: int, session: Session = Depends(get_session)) -> None:
    r = session.get(Recording, recording_id)
    if not r:
        raise HTTPException(404)
    if r.status == "recording":
        raise HTTPException(400, "stop the recording before deleting")
    session.exec(delete(Segment).where(Segment.recording_id == recording_id))  # type: ignore[arg-type]
    session.exec(delete(Summary).where(Summary.recording_id == recording_id))  # type: ignore[arg-type]
    session.exec(delete(QAMessage).where(QAMessage.recording_id == recording_id))  # type: ignore[arg-type]
    session.delete(r)
    session.commit()
    # best-effort removal of on-disk audio
    rec_dir = Path(settings.db_path).resolve().parent / "recordings" / str(recording_id)
    if rec_dir.exists():
        shutil.rmtree(rec_dir, ignore_errors=True)


class SummarizeRequest(BaseModel):
    template_id: int


@router.post("/{recording_id}/summarize")
async def summarize_recording(recording_id: int, payload: SummarizeRequest) -> dict[str, str | int]:
    if runtime.pipeline is None:
        raise HTTPException(503, "pipeline not running")
    s = await runtime.pipeline.summarize(recording_id=recording_id, template_id=payload.template_id)
    return {"summary_id": s.id or 0, "content": s.content}


class AskRequest(BaseModel):
    question: str
    template_id: int | None = None


@router.post("/{recording_id}/ask")
async def ask_recording(recording_id: int, payload: AskRequest) -> dict[str, str]:
    if runtime.pipeline is None:
        raise HTTPException(503, "pipeline not running")
    answer = await runtime.pipeline.ask(
        recording_id=recording_id, question=payload.question, template_id=payload.template_id
    )
    return {"answer": answer}


@router.get("/{recording_id}/export")
def export_recording(recording_id: int, format: str = "md") -> Response:
    if format not in {"md", "txt"}:
        raise HTTPException(400, "format must be md or txt")
    body = export_markdown(recording_id) if format == "md" else export_text(recording_id)
    media_type = "text/markdown" if format == "md" else "text/plain"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=recording-{recording_id}.{format}"},
    )
