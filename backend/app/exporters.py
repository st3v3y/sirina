from __future__ import annotations

from sqlmodel import Session, select

from .db import engine
from .models import Recording, Segment, Summary


def _format_ts(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def export_markdown(recording_id: int) -> str:
    with Session(engine) as s:
        r = s.get(Recording, recording_id)
        if r is None:
            raise ValueError("recording not found")
        segs = s.exec(
            select(Segment).where(Segment.recording_id == recording_id).order_by(Segment.start_ts)
        ).all()
        sums = s.exec(
            select(Summary).where(Summary.recording_id == recording_id).order_by(Summary.created_at)
        ).all()

    lines: list[str] = []
    title = r.title or f"Recording #{r.id}"
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- Started: {r.started_at.isoformat()}")
    if r.ended_at:
        lines.append(f"- Ended: {r.ended_at.isoformat()}")
    lines.append("")
    if sums:
        latest = sorted(sums, key=lambda s: s.created_at)[-1]
        lines.append("## Summary")
        lines.append("")
        for section in latest.sections or []:
            lines.append(f"### {section.get('title', '')}")
            lines.append("")
            lines.append(str(section.get("content", "")).strip())
            lines.append("")
    lines.append("## Transcript")
    lines.append("")
    for seg in segs:
        lines.append(f"**[{_format_ts(seg.start_ts)}] {seg.speaker_label}:** {seg.text}")
    return "\n".join(lines) + "\n"


def export_text(recording_id: int) -> str:
    with Session(engine) as s:
        r = s.get(Recording, recording_id)
        if r is None:
            raise ValueError("recording not found")
        segs = s.exec(
            select(Segment).where(Segment.recording_id == recording_id).order_by(Segment.start_ts)
        ).all()

    lines = [r.title or f"Recording #{r.id}", ""]
    for seg in segs:
        lines.append(f"[{_format_ts(seg.start_ts)}] {seg.speaker_label}: {seg.text}")
    return "\n".join(lines) + "\n"
