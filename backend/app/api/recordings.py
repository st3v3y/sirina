from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlmodel import Session, delete, select

from ..audio import system_capture
from ..config import settings
from ..db import get_session
from ..exporters import export_markdown, export_text
from ..models import Person, QAMessage, Recording, RecordingTag, Segment, Speaker, Summary, Tag
from ..runtime import runtime
from ..speakers import display_name

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recordings", tags=["recordings"])


class SpeakerOut(BaseModel):
    id: int
    label: str
    name: str  # resolved display name (Person name or label)
    person_id: int | None
    color: str | None


class StartRequest(BaseModel):
    title: str | None = None
    device: str | None = None          # primary (mic) input device name or index
    system_device: str | None = None   # loopback system-audio device (e.g. BlackHole)
    system_source: str | None = None   # "native" | "device" | "none" (default inferred)


class ProgressOut(BaseModel):
    stage: str  # queued | transcribing | diarizing | summarizing | done
    fraction: float | None = None  # 0..1 when available, else null (indeterminate)
    elapsed_s: float | None = None  # seconds since processing started
    estimated: bool = False  # True if fraction is a time-based estimate (MLX)


def _progress_for(recording_id: int) -> "ProgressOut | None":
    p = runtime.processor.progress_for(recording_id) if runtime.processor else None
    return ProgressOut(**p) if p else None


class RecordingListItem(BaseModel):
    id: int
    title: str | None
    started_at: datetime
    ended_at: datetime | None
    duration_s: float | None
    status: str
    error: str | None = None
    progress: ProgressOut | None = None
    segment_count: int
    tags: list[Tag]


class RecordingDetail(BaseModel):
    id: int
    title: str | None
    started_at: datetime
    ended_at: datetime | None
    duration_s: float | None
    status: str
    error: str | None
    warning: str | None = None  # non-fatal capture issue, e.g. a source track ended short
    progress: ProgressOut | None = None
    language: str | None
    tags: list[Tag]
    tracks: list[str]  # which audio tracks exist on disk: mixed | mic | system
    speakers: list[SpeakerOut]
    segments: list[Segment]
    summaries: list[Summary]
    qa: list[QAMessage]


class ActiveInfo(BaseModel):
    id: int
    elapsed_s: float
    level: float  # max of all tracks (kept for back-compat)
    mic_level: float = 0.0
    system_level: float = 0.0
    mic_healthy: bool = True
    system_healthy: bool | None = None  # None when there is no system track
    system_restarts: int = 0


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

    # Resolve the system-audio source. Backwards-compatible default: a system_device
    # implies the device (loopback) path, otherwise no system track.
    source = (payload.system_source or ("device" if payload.system_device else "none")).lower()
    if source not in {"native", "device", "none"}:
        raise HTTPException(400, "system_source must be native, device, or none")
    if source == "native" and not system_capture.native_available():
        raise HTTPException(
            400,
            "Native system-audio capture is unavailable. Grant Screen Recording permission "
            "(System Settings → Privacy & Security → Screen Recording), or pick a loopback "
            "device (e.g. BlackHole) instead.",
        )
    if source == "device" and not payload.system_device:
        raise HTTPException(400, "system_source 'device' requires a system_device")

    try:
        recording_id = await runtime.recorder.start(
            device=_coerce(payload.device),
            system_device=_coerce(payload.system_device),
            title=payload.title,
            system_source=source,
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


@router.post("/{recording_id}/reprocess")
async def reprocess_recording(
    recording_id: int, session: Session = Depends(get_session)
) -> dict[str, bool]:
    """Re-run transcription for a recording (e.g. after a failure). The job is
    idempotent — it clears prior segments/speakers and rebuilds them."""
    r = session.get(Recording, recording_id)
    if not r:
        raise HTTPException(404)
    if r.status == "recording":
        raise HTTPException(400, "recording is still in progress")
    if runtime.processor is None:
        raise HTTPException(503, "processor not running")
    r.status = "processing"
    r.error = None
    session.add(r)
    session.commit()
    await runtime.processor.enqueue(recording_id)
    return {"ok": True}


@router.post("/{recording_id}/cancel-diarization")
async def cancel_diarization(recording_id: int) -> dict[str, bool]:
    """Ask the processor to skip diarization for this recording (keep the baseline
    speaker split) and proceed to the summary. No-op if it is not diarizing."""
    if runtime.processor is None:
        raise HTTPException(503, "processor not running")
    runtime.processor.cancel_diarization(recording_id)
    return {"ok": True}


@router.get("/active", response_model=ActiveInfo | None)
async def active_recording() -> ActiveInfo | None:
    if runtime.recorder is None:
        return None
    info = runtime.recorder.active_info()
    return ActiveInfo(**info) if info else None


def _tags_by_recording(session: Session, recording_ids: list[int]) -> dict[int, list[Tag]]:
    """Batch-load tags for a set of recordings (avoids N+1)."""
    if not recording_ids:
        return {}
    rows = session.exec(
        select(RecordingTag.recording_id, Tag)
        .join(Tag, Tag.id == RecordingTag.tag_id)  # type: ignore[arg-type]
        .where(RecordingTag.recording_id.in_(recording_ids))  # type: ignore[attr-defined]
    ).all()
    out: dict[int, list[Tag]] = {}
    for rec_id, tag in rows:
        out.setdefault(rec_id, []).append(tag)
    return out


@router.get("", response_model=list[RecordingListItem])
def list_recordings(
    tag_id: int | None = None, session: Session = Depends(get_session)
) -> list[RecordingListItem]:
    stmt = select(Recording)
    if tag_id is not None:
        stmt = stmt.join(RecordingTag, RecordingTag.recording_id == Recording.id).where(  # type: ignore[arg-type]
            RecordingTag.tag_id == tag_id
        )
    recs = session.exec(stmt.order_by(Recording.started_at.desc())).all()  # type: ignore[attr-defined]
    tags_map = _tags_by_recording(session, [r.id for r in recs if r.id is not None])
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
                error=r.error,
                progress=_progress_for(r.id),
                segment_count=len(count),
                tags=tags_map.get(r.id, []),  # type: ignore[arg-type]
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
        select(Summary).where(Summary.recording_id == recording_id).order_by(Summary.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    qa = session.exec(
        select(QAMessage).where(QAMessage.recording_id == recording_id).order_by(QAMessage.created_at)  # type: ignore[arg-type]
    ).all()
    speakers = session.exec(
        select(Speaker).where(Speaker.recording_id == recording_id).order_by(Speaker.id)  # type: ignore[arg-type]
    ).all()
    persons = {p.id: p.name for p in session.exec(select(Person)).all() if p.id is not None}
    speakers_out = [
        SpeakerOut(id=sp.id, label=sp.label, name=display_name(sp, persons), person_id=sp.person_id, color=sp.color)  # type: ignore[arg-type]
        for sp in speakers
    ]
    tags = _tags_by_recording(session, [recording_id]).get(recording_id, [])
    tracks = [
        name
        for name, p in (("mixed", r.audio_path), ("mic", r.mic_path), ("system", r.system_path))
        if p and Path(p).exists()
    ]
    return RecordingDetail(
        id=r.id,  # type: ignore[arg-type]
        title=r.title,
        started_at=r.started_at,
        ended_at=r.ended_at,
        duration_s=r.duration_s,
        status=r.status,
        error=r.error,
        warning=r.warning,
        progress=_progress_for(r.id),
        language=r.language,
        tags=tags,
        tracks=tracks,
        speakers=speakers_out,
        segments=list(segments),
        summaries=list(summaries),
        qa=list(qa),
    )


class RecordingUpdate(BaseModel):
    title: str | None = None


@router.patch("/{recording_id}", response_model=RecordingListItem)
def update_recording(
    recording_id: int, payload: RecordingUpdate, session: Session = Depends(get_session)
) -> RecordingListItem:
    r = session.get(Recording, recording_id)
    if not r:
        raise HTTPException(404)
    # Empty string clears the title (UI falls back to "Recording #<id>").
    title = (payload.title or "").strip()
    r.title = title or None
    session.add(r)
    session.commit()
    session.refresh(r)
    count = session.exec(select(Segment.id).where(Segment.recording_id == recording_id)).all()  # type: ignore[arg-type]
    tags = _tags_by_recording(session, [recording_id]).get(recording_id, [])
    return RecordingListItem(
        id=r.id,  # type: ignore[arg-type]
        title=r.title,
        started_at=r.started_at,
        ended_at=r.ended_at,
        duration_s=r.duration_s,
        status=r.status,
        error=r.error,
        progress=_progress_for(r.id),
        segment_count=len(count),
        tags=tags,
    )


@router.delete("/{recording_id}", status_code=204)
def delete_recording(recording_id: int, session: Session = Depends(get_session)) -> None:
    r = session.get(Recording, recording_id)
    if not r:
        raise HTTPException(404)
    if r.status == "recording":
        raise HTTPException(400, "stop the recording before deleting")
    session.exec(delete(Segment).where(Segment.recording_id == recording_id))  # type: ignore[arg-type]
    session.exec(delete(Speaker).where(Speaker.recording_id == recording_id))  # type: ignore[arg-type]
    session.exec(delete(Summary).where(Summary.recording_id == recording_id))  # type: ignore[arg-type]
    session.exec(delete(QAMessage).where(QAMessage.recording_id == recording_id))  # type: ignore[arg-type]
    session.exec(delete(RecordingTag).where(RecordingTag.recording_id == recording_id))  # type: ignore[arg-type]
    session.delete(r)
    session.commit()
    # best-effort removal of on-disk audio
    rec_dir = settings.recordings_dir / str(recording_id)
    if rec_dir.exists():
        shutil.rmtree(rec_dir, ignore_errors=True)


class TagAssign(BaseModel):
    tag_id: int


@router.post("/{recording_id}/tags", status_code=204)
def add_tag(recording_id: int, payload: TagAssign, session: Session = Depends(get_session)) -> None:
    if not session.get(Recording, recording_id):
        raise HTTPException(404, "recording not found")
    if not session.get(Tag, payload.tag_id):
        raise HTTPException(404, "tag not found")
    exists = session.get(RecordingTag, (recording_id, payload.tag_id))
    if exists is None:
        session.add(RecordingTag(recording_id=recording_id, tag_id=payload.tag_id))
        session.commit()


@router.delete("/{recording_id}/tags/{tag_id}", status_code=204)
def remove_tag(recording_id: int, tag_id: int, session: Session = Depends(get_session)) -> None:
    session.exec(
        delete(RecordingTag).where(
            RecordingTag.recording_id == recording_id, RecordingTag.tag_id == tag_id  # type: ignore[arg-type]
        )
    )
    session.commit()


class SummarizeRequest(BaseModel):
    template_id: int


@router.post("/{recording_id}/summarize", response_model=Summary)
async def summarize_recording(recording_id: int, payload: SummarizeRequest) -> Summary:
    if runtime.pipeline is None:
        raise HTTPException(503, "pipeline not running")
    return await runtime.pipeline.summarize(recording_id=recording_id, template_id=payload.template_id)


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


class SpeakerRenameRequest(BaseModel):
    name: str


@router.put("/{recording_id}/speakers/{speaker_id}", response_model=SpeakerOut)
def rename_speaker(
    recording_id: int,
    speaker_id: int,
    payload: SpeakerRenameRequest,
    session: Session = Depends(get_session),
) -> SpeakerOut:
    sp = session.get(Speaker, speaker_id)
    if not sp or sp.recording_id != recording_id:
        raise HTTPException(404)
    name = payload.name.strip()
    # Empty or the speaker's own default label means "no real name": never create
    # a Person from a default label (that produced junk "Speaker 1"/"You" People).
    # Treat it as clearing any existing link, reverting to the default label.
    if not name or name == sp.label:
        sp.person_id = None
        session.add(sp)
        session.commit()
        session.refresh(sp)
        persons = {p.id: p.name for p in session.exec(select(Person)).all() if p.id is not None}
        return SpeakerOut(
            id=sp.id, label=sp.label, name=display_name(sp, persons), person_id=None, color=sp.color  # type: ignore[arg-type]
        )
    # Find-or-create the Person (case-insensitive match on existing names).
    person = session.exec(select(Person).where(Person.name == name)).first()
    if person is None:
        existing = session.exec(select(Person)).all()
        person = next((p for p in existing if p.name.lower() == name.lower()), None)
    if person is None:
        person = Person(name=name)
        session.add(person)
        session.flush()
    sp.person_id = person.id
    session.add(sp)
    session.commit()
    session.refresh(sp)
    return SpeakerOut(id=sp.id, label=sp.label, name=name, person_id=sp.person_id, color=sp.color)  # type: ignore[arg-type]


@router.get("/{recording_id}/audio")
def get_audio(recording_id: int, track: str = "mixed", session: Session = Depends(get_session)) -> FileResponse:
    """Serve a recording's audio track for playback (mixed | mic | system).
    FileResponse handles HTTP range requests, so the browser can seek."""
    if track not in {"mixed", "mic", "system"}:
        raise HTTPException(400, "track must be mixed, mic, or system")
    r = session.get(Recording, recording_id)
    if not r:
        raise HTTPException(404)
    path = {"mixed": r.audio_path, "mic": r.mic_path, "system": r.system_path}.get(track)
    if not path or not Path(path).exists():
        raise HTTPException(404, f"no {track} track for this recording")
    return FileResponse(path, media_type="audio/wav", filename=f"recording-{recording_id}-{track}.wav")


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
