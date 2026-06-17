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
from .models import (
    ChatMessage,
    ChatSession,
    PromptTemplate,
    QAMessage,
    Recording,
    Segment,
    Summary,
    SummaryTemplate,
)
from .speakers import speaker_names
from .transcribe.whisper import FasterWhisperWorker

log = logging.getLogger(__name__)

# Char budget for concatenated transcripts in a cross-recording chat answer.
CROSS_CONTEXT_CHAR_BUDGET = 24000


class Pipeline:
    def __init__(self, whisper: FasterWhisperWorker, ollama: OllamaClient) -> None:
        self.whisper = whisper
        self.ollama = ollama

    def _transcript(self, session: Session, recording_id: int) -> str:
        segs = session.exec(
            select(Segment).where(Segment.recording_id == recording_id).order_by(Segment.start_ts)
        ).all()
        names = speaker_names(session, recording_id)
        return "\n".join(f"{names.get(seg.speaker_id, 'Speaker')}: {seg.text}" for seg in segs)

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
            general_context = (tmpl.general_context or "").strip()
            meta = {
                "transcript": transcript,
                "title": (rec.title if rec else None) or f"Recording {recording_id}",
                "date": (rec.started_at.date().isoformat() if rec else date.today().isoformat()),
            }

        produced: list[dict[str, str]] = []
        for section in sections_def:
            title = section.get("title", "")
            source = section.get("prompt", "")
            prompt = render(source, meta)
            # Auto-supply the transcript so authors don't have to add the placeholder;
            # skip if they already reference it (avoids a duplicate copy).
            if "{{transcript}}" not in source:
                prompt = f"{prompt}\n\nTRANSCRIPT:\n{transcript}"
            # Prepend the template's general context (framing) to every section.
            if general_context:
                prompt = f"{general_context}\n\n{prompt}"
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

    async def cross_ask(self, session_id: int, question: str) -> str:
        """Answer a question across all `ready` recordings' transcripts, newest-first
        up to a char budget, and persist the turn to the chat session."""
        with Session(engine) as s:
            if s.get(ChatSession, session_id) is None:
                raise ValueError("chat session not found")
            recs = s.exec(
                select(Recording)
                .where(Recording.status == "ready")
                .order_by(Recording.started_at.desc())  # type: ignore[attr-defined]
            ).all()
            blocks: list[str] = []
            used = 0
            omitted = 0
            for rec in recs:
                transcript = self._transcript(s, rec.id)  # type: ignore[arg-type]
                if not transcript.strip():
                    continue
                header = f"### {rec.title or f'Recording {rec.id}'} ({rec.started_at.date().isoformat()})"
                block = f"{header}\n{transcript}"
                if blocks and used + len(block) > CROSS_CONTEXT_CHAR_BUDGET:
                    omitted += 1
                    continue
                blocks.append(block)
                used += len(block)
            history = s.exec(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at)
            ).all()

        context = "\n\n".join(blocks) or "(no transcripts available)"
        hist_text = "\n".join(f"{m.role.upper()}: {m.content}" for m in history)
        prompt = (
            "You are an assistant answering questions across multiple meeting transcripts. "
            "Use ONLY the transcripts and prior Q&A below. If the answer isn't supported, say so.\n\n"
            f"TRANSCRIPTS:\n{context}\n\n"
            f"PRIOR Q&A:\n{hist_text or '(none)'}\n\n"
            f"QUESTION:\n{question}\n\nANSWER:"
        )
        response = await self.ollama.generate(prompt)
        answer = response or "(no answer)"
        if omitted:
            answer += f"\n\n_(Note: {omitted} older recording(s) were omitted to fit the context window.)_"
        with Session(engine) as s:
            s.add(ChatMessage(session_id=session_id, role="user", content=question))
            s.add(ChatMessage(session_id=session_id, role="assistant", content=answer))
            s.commit()
        return answer
