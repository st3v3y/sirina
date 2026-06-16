"""Post-recording LLM helpers (summaries + Q&A) over a recording's transcript.

Recording/transcription no longer happen here — capture is owned by
`app/recording/recorder.py`, and transcription is a separate (later) job.
These methods operate on whatever Segments exist for a recording; until the
transcription job is built they simply have nothing to work with.
"""
from __future__ import annotations

import logging
from datetime import date

from sqlmodel import Session, select

from .db import engine
from .llm.ollama_client import OllamaClient, render
from .models import PromptTemplate, QAMessage, Recording, Segment, Summary, SummaryTemplate
from .transcribe.whisper import FasterWhisperWorker

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, whisper: FasterWhisperWorker, ollama: OllamaClient) -> None:
        self.whisper = whisper
        self.ollama = ollama

    def _transcript(self, session: Session, recording_id: int) -> str:
        segs = session.exec(
            select(Segment).where(Segment.recording_id == recording_id).order_by(Segment.start_ts)
        ).all()
        return "\n".join(f"{seg.speaker_label}: {seg.text}" for seg in segs)

    def default_summary_template_id(self) -> int | None:
        with Session(engine) as s:
            t = s.exec(
                select(SummaryTemplate).where(SummaryTemplate.is_default == True)  # noqa: E712
            ).first()
            return t.id if t else None

    async def summarize(self, recording_id: int, template_id: int) -> Summary:
        """Generate a multi-section summary: one LLM call per template section."""
        with Session(engine) as s:
            tmpl = s.get(SummaryTemplate, template_id)
            if tmpl is None:
                raise ValueError(f"summary template {template_id} not found")
            rec = s.get(Recording, recording_id)
            transcript = self._transcript(s, recording_id)
            sections_def = list(tmpl.sections or [])
            meta = {
                "transcript": transcript,
                "title": (rec.title if rec else None) or f"Recording {recording_id}",
                "date": (rec.started_at.date().isoformat() if rec else date.today().isoformat()),
            }

        produced: list[dict[str, str]] = []
        for section in sections_def:
            title = section.get("title", "")
            prompt = render(section.get("prompt", ""), meta)
            content = await self.ollama.generate(prompt)
            produced.append({"title": title, "content": content})

        with Session(engine) as s:
            summary = Summary(recording_id=recording_id, template_id=template_id, sections=produced)
            s.add(summary)
            s.commit()
            s.refresh(summary)
        return summary

    async def ask(self, recording_id: int, question: str, template_id: int | None) -> str:
        with Session(engine) as s:
            tmpl_id = template_id or self._default_qa_template_id()
            if tmpl_id is None:
                raise ValueError("no qa template available")
            tmpl = s.get(PromptTemplate, tmpl_id)
            if tmpl is None:
                raise ValueError("qa template not found")
            transcript = self._transcript(s, recording_id)
            history = s.exec(
                select(QAMessage)
                .where(QAMessage.recording_id == recording_id)
                .order_by(QAMessage.created_at)
            ).all()
        qa_history = "\n".join(f"{m.role.upper()}: {m.content}" for m in history)
        prompt = render(
            tmpl.body,
            {
                "transcript": transcript,
                "qa_history": qa_history or "(none)",
                "question": question,
            },
        )
        response = await self.ollama.generate(prompt)
        with Session(engine) as s:
            s.add(QAMessage(recording_id=recording_id, role="user", content=question))
            s.add(QAMessage(recording_id=recording_id, role="assistant", content=response or "(no answer)"))
            s.commit()
        return response

    def _default_qa_template_id(self) -> int | None:
        with Session(engine) as s:
            t = s.exec(
                select(PromptTemplate).where(PromptTemplate.is_default == True)  # noqa: E712
            ).first()
            return t.id if t else None
