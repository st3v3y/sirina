"""Post-recording LLM helpers (summaries + Q&A) over a recording's transcript.

Recording/transcription no longer happen here — capture is owned by
`app/recording/recorder.py`, and transcription is a separate (later) job.
These methods operate on whatever Segments exist for a recording; until the
transcription job is built they simply have nothing to work with.
"""
from __future__ import annotations

import logging

from sqlmodel import Session, select

from .db import engine
from .llm.ollama_client import OllamaClient, render
from .models import PromptTemplate, QAMessage, Segment, Summary
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

    async def summarize(self, recording_id: int, template_id: int) -> Summary:
        with Session(engine) as s:
            tmpl = s.get(PromptTemplate, template_id)
            if tmpl is None:
                raise ValueError(f"template {template_id} not found")
            transcript = self._transcript(s, recording_id)
        prompt = render(tmpl.body, {"transcript": transcript})
        response = await self.ollama.generate(prompt)
        with Session(engine) as s:
            summary = Summary(
                recording_id=recording_id,
                kind="full",
                template_id=template_id,
                content=response,
            )
            s.add(summary)
            s.commit()
            s.refresh(summary)
        return summary

    async def ask(self, recording_id: int, question: str, template_id: int | None) -> str:
        with Session(engine) as s:
            tmpl_id = template_id or self._default_template_id("qa")
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

    def _default_template_id(self, kind: str) -> int | None:
        with Session(engine) as s:
            t = s.exec(
                select(PromptTemplate)
                .where(PromptTemplate.kind == kind)
                .where(PromptTemplate.is_default == True)  # noqa: E712
            ).first()
            return t.id if t else None
