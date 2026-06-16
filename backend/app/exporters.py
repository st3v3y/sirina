from __future__ import annotations

from sqlmodel import Session, select

from .db import engine
from .models import Meeting, Segment, Summary


def _format_ts(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def export_markdown(meeting_id: int) -> str:
    with Session(engine) as s:
        m = s.get(Meeting, meeting_id)
        if m is None:
            raise ValueError("meeting not found")
        segs = s.exec(select(Segment).where(Segment.meeting_id == meeting_id).order_by(Segment.start_ts)).all()
        sums = s.exec(select(Summary).where(Summary.meeting_id == meeting_id).order_by(Summary.created_at)).all()

    lines: list[str] = []
    title = m.title or f"Meeting #{m.id}"
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- Started: {m.started_at.isoformat()}")
    if m.ended_at:
        lines.append(f"- Ended: {m.ended_at.isoformat()}")
    lines.append("")
    full = [s for s in sums if s.kind == "full"]
    if full:
        lines.append("## Summary")
        lines.append("")
        lines.append(full[-1].content)
        lines.append("")
    lines.append("## Transcript")
    lines.append("")
    for seg in segs:
        lines.append(f"**[{_format_ts(seg.start_ts)}] {seg.username}:** {seg.text}")
    return "\n".join(lines) + "\n"


def export_text(meeting_id: int) -> str:
    with Session(engine) as s:
        m = s.get(Meeting, meeting_id)
        if m is None:
            raise ValueError("meeting not found")
        segs = s.exec(select(Segment).where(Segment.meeting_id == meeting_id).order_by(Segment.start_ts)).all()

    lines = [m.title or f"Meeting #{m.id}", ""]
    for seg in segs:
        lines.append(f"[{_format_ts(seg.start_ts)}] {seg.username}: {seg.text}")
    return "\n".join(lines) + "\n"
