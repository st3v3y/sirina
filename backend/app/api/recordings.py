from __future__ import annotations

import asyncio
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, delete, select

from ..audio import system_capture
from ..config import settings
from ..db import get_session
from ..exporters import export_markdown, export_text
from ..models import Person, QAMessage, Recording, RecordingTag, Segment, Speaker, Summary, Tag
from ..llm.provider import LLMError
from ..recording.recorder import apply_trim, recover_orphaned
from ..runtime import runtime
from ..speakers import SELF_LABEL, display_name
from .. import voiceprints

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
    pending_trim: dict | None = None  # {leading_s, trailing_s, ...} when awaiting a trim decision
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


class StopResult(BaseModel):
    ok: bool = True
    # Present when the recording has a long stretch of leading/trailing silence: it is HELD
    # (not yet transcribing) until the client calls /trim-decision. Absent → already enqueued.
    trim: dict | None = None


@router.post("/{recording_id}/stop", response_model=StopResult)
async def stop_recording(recording_id: int) -> StopResult:
    if runtime.recorder is None:
        raise HTTPException(503, "recorder not running")
    suggestion = await runtime.recorder.stop(recording_id)
    # With a trim suggestion the recording is held awaiting the user's decision; otherwise
    # hand off to the background transcription processor (recording is now `processing`).
    if suggestion is None and runtime.processor is not None:
        await runtime.processor.enqueue(recording_id)
    return StopResult(trim=suggestion)


class TrimDecision(BaseModel):
    trim: bool  # True = trim the detected silence, False = keep the full recording


@router.post("/{recording_id}/trim-decision")
async def trim_decision(
    recording_id: int, payload: TrimDecision, session: Session = Depends(get_session)
) -> dict[str, bool]:
    """Resolve a held recording (one stopped with long leading/trailing silence): either
    trim the detected window or keep the full take, then enqueue it for transcription."""
    r = session.get(Recording, recording_id)
    if not r:
        raise HTTPException(404)
    if not r.pending_trim:
        raise HTTPException(400, "recording is not awaiting a trim decision")
    if payload.trim:
        window = json.loads(r.pending_trim)
        # Rewriting the (possibly gigabyte-sized) WAVs is blocking CPU/IO — off the loop.
        await asyncio.to_thread(
            apply_trim, recording_id, float(window["start_s"]), float(window["end_s"])
        )
        session.expire(r)  # apply_trim updated the row (incl. clearing pending_trim) elsewhere
    else:
        r.pending_trim = None
        session.add(r)
        session.commit()
    r = session.get(Recording, recording_id)
    if r is None:  # deleted concurrently — a 404 beats a 500 here
        raise HTTPException(404)
    r.status = "processing"
    r.error = None
    session.add(r)
    session.commit()
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
    if r.status != "recording" and not r.audio_path:
        raise HTTPException(400, "this recording's audio was deleted — re-processing is unavailable")
    if r.status == "recording":
        # Distinguish a genuinely live capture from one orphaned by a crash/force-quit
        # (its files are on disk but were never finalized). Only the recorder's currently
        # active recording is truly in progress; anything else is stale and recoverable.
        active = runtime.recorder.active_info() if runtime.recorder is not None else None
        if active is not None and active.get("id") == recording_id:
            raise HTTPException(400, "recording is still in progress")
        # Mixing the recovered tracks is blocking CPU/IO — run it off the event loop.
        if not await asyncio.to_thread(recover_orphaned, recording_id):
            raise HTTPException(400, "this recording captured no audio to process")
        session.expire(r)  # recover_orphaned updated the row in its own session
    if runtime.processor is None:
        raise HTTPException(503, "processor not running")
    # Double-click / already-running guard: enqueue() also dedupes, but reject loudly
    # when the job is mid-flight so the UI can say why nothing new happened.
    if runtime.processor.current_id() == recording_id:
        raise HTTPException(409, "this recording is already being processed")
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


@router.post("/{recording_id}/cancel-processing")
async def cancel_processing(recording_id: int) -> dict[str, bool]:
    """Stop processing this recording after the current uninterruptible step. Any transcript
    already produced is kept (it finalizes as `ready`); remaining stages are skipped. No-op if
    it isn't being processed."""
    if runtime.processor is None:
        raise HTTPException(503, "processor not running")
    runtime.processor.cancel_processing(recording_id)
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
    # One grouped COUNT for all recordings — a per-recording query that materialized
    # every segment id was an N+1 that transferred hundreds of thousands of rows.
    counts = dict(
        session.exec(
            select(Segment.recording_id, func.count()).group_by(Segment.recording_id)  # type: ignore[arg-type]
        ).all()
    )
    out: list[RecordingListItem] = []
    for r in recs:
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
                segment_count=counts.get(r.id, 0),
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
        pending_trim=json.loads(r.pending_trim) if r.pending_trim else None,
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
    count = session.exec(
        select(func.count()).select_from(Segment).where(Segment.recording_id == recording_id)  # type: ignore[arg-type]
    ).one()
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
        segment_count=count,
        tags=tags,
    )


@router.delete("/{recording_id}/audio", status_code=204)
def delete_recording_audio(recording_id: int, session: Session = Depends(get_session)) -> None:
    """Delete only the on-disk audio for a recording, keeping its transcript, summary,
    Q&A and tags. Irreversible: playback and Re-process become unavailable."""
    r = session.get(Recording, recording_id)
    if not r:
        raise HTTPException(404)
    if r.status in {"recording", "processing"}:
        raise HTTPException(400, "wait until the recording has finished processing")
    for p in (r.mic_path, r.system_path, r.audio_path):
        if p:
            Path(p).unlink(missing_ok=True)
    # The per-recording directory only ever holds audio tracks — remove it wholesale so
    # nothing lingers (e.g. a stray WAV left behind after compression).
    rec_dir = settings.recordings_dir / str(recording_id)
    if rec_dir.exists():
        shutil.rmtree(rec_dir, ignore_errors=True)
    r.mic_path = None
    r.system_path = None
    r.audio_path = None
    session.add(r)
    session.commit()


@router.delete("/{recording_id}", status_code=204)
def delete_recording(recording_id: int, session: Session = Depends(get_session)) -> None:
    r = session.get(Recording, recording_id)
    if not r:
        raise HTTPException(404)
    if r.status == "recording":
        raise HTTPException(400, "stop the recording before deleting")
    # Deleting mid-job would yank rows and audio out from under the processor (its next
    # _write_tracks re-inserts speakers/segments for the gone recording). Same guard as
    # delete_recording_audio: stop processing first, then delete.
    if r.status == "processing":
        raise HTTPException(400, "stop processing before deleting (use Stop, then delete)")
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
    try:
        return await runtime.pipeline.summarize(
            recording_id=recording_id, template_id=payload.template_id
        )
    except LLMError as e:
        raise HTTPException(502, str(e)) from e


class AskRequest(BaseModel):
    question: str
    template_id: int | None = None


@router.post("/{recording_id}/ask")
async def ask_recording(recording_id: int, payload: AskRequest) -> dict[str, str]:
    if runtime.pipeline is None:
        raise HTTPException(503, "pipeline not running")
    try:
        answer = await runtime.pipeline.ask(
            recording_id=recording_id, question=payload.question, template_id=payload.template_id
        )
    except LLMError as e:
        raise HTTPException(502, str(e)) from e
    return {"answer": answer}


class SpeakerRenameRequest(BaseModel):
    name: str


def _withdraw_enrollment(session: Session, sp: Speaker) -> None:
    """Undo this speaker's contribution to its linked Person's voiceprint (used when
    the link is cleared or moved to a different person — a corrected rename must not
    leave the mis-attributed voice sample in the old fingerprint)."""
    if not sp.enrolled:
        return
    old = session.get(Person, sp.person_id) if sp.person_id else None
    embedding = voiceprints.decode(sp.embedding)
    if old is not None and embedding is not None:
        voiceprints.withdraw(old, embedding)
        session.add(old)
    sp.enrolled = False
    session.add(sp)


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
    # The "You" speaker is bound to the singleton self-Person: rename THAT (an empty value
    # reverts it to "You"), so the app user is one reusable Person, never unlinked or
    # duplicated into a second "Stefan" entry.
    if sp.person_id is not None:
        linked = session.get(Person, sp.person_id)
        if linked is not None and linked.is_self:
            linked.name = name or SELF_LABEL
            session.add(linked)
            session.commit()
            session.refresh(sp)
            return SpeakerOut(
                id=sp.id, label=sp.label, name=linked.name, person_id=sp.person_id, color=sp.color  # type: ignore[arg-type]
            )
    # Empty or the speaker's own default label means "no real name": never create
    # a Person from a default label (that produced junk "Speaker 1"/"You" People).
    # Treat it as clearing any existing link, reverting to the default label.
    if not name or name == sp.label:
        _withdraw_enrollment(session, sp)
        sp.person_id = None
        session.add(sp)
        session.commit()
        session.refresh(sp)
        persons = {p.id: p.name for p in session.exec(select(Person)).all() if p.id is not None}
        return SpeakerOut(
            id=sp.id, label=sp.label, name=display_name(sp, persons), person_id=None, color=sp.color  # type: ignore[arg-type]
        )
    # Find-or-create the Person (case-insensitive match, done in SQL).
    person = session.exec(
        select(Person).where(func.lower(Person.name) == name.lower())
    ).first()
    if person is None:
        person = Person(name=name)
        session.add(person)
        session.flush()
    if sp.person_id is not None and sp.person_id != person.id:
        _withdraw_enrollment(session, sp)  # corrected rename: pull the sample back out
    sp.person_id = person.id
    session.add(sp)
    # A manual rename is confirmed ground truth: enroll this speaker's voice embedding
    # into the person's fingerprint so they're auto-recognised in future recordings.
    # At most once per speaker (`enrolled`) — a repeated or corrected rename must not
    # double-count the same sample in the running mean.
    embedding = voiceprints.decode(sp.embedding)
    if embedding is not None and not person.is_self and not sp.enrolled:
        voiceprints.enroll(person, embedding)
        sp.enrolled = True
        session.add(person)
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
    # `inline` (not the default `attachment`): WebKit/WKWebView — the Tauri webview —
    # refuses to play <audio>/<video> served with `Content-Disposition: attachment`,
    # so the player would render but produce no sound. Inline keeps it seekable.
    suffix = Path(path).suffix.lower()  # .wav, or .m4a once compressed
    return FileResponse(
        path,
        media_type="audio/mp4" if suffix == ".m4a" else "audio/wav",
        filename=f"recording-{recording_id}-{track}{suffix}",
        content_disposition_type="inline",
    )


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
