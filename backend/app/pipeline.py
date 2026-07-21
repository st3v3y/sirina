"""Post-recording LLM helpers (summaries + Q&A) over a recording's transcript.

Recording/transcription no longer happen here — capture is owned by
`app/recording/recorder.py`, and transcription is a separate (later) job.
These methods operate on whatever Segments exist for a recording; until the
transcription job is built they simply have nothing to work with.
"""
from __future__ import annotations

import logging
import re
from datetime import date

from sqlmodel import Session, select

from .config import settings
from .db import engine
from .llm.provider import OpenAICompatProvider, render
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

# All LLM features size their transcript budget from the AI context-window setting
# (`llm_context_tokens`). Rough chars-per-token ratio; reserve room for the question,
# prior Q&A, the system prompt, and the answer itself.
CHARS_PER_TOKEN = 3.5
CONTEXT_RESERVE_TOKENS = 1024
DEFAULT_CONTEXT_TOKENS = 8192


def _context_budget() -> int:
    ctx = settings.llm_context_tokens or DEFAULT_CONTEXT_TOKENS
    return max(4000, int((ctx - CONTEXT_RESERVE_TOKENS) * CHARS_PER_TOKEN))


# Kept under the old name for cross_ask readability.
_cross_context_budget = _context_budget

TRUNCATION_MARKER = "[… middle of the transcript omitted to fit the AI context window …]"


def fit_transcript(transcript: str, budget: int | None = None) -> str:
    """Fit a transcript into the model's context budget by cutting the MIDDLE out
    (openings set the topic, endings hold decisions/next steps — the middle is the
    safest loss). Without this, over-long prompts either fail outright on cloud
    providers or get silently tail-truncated by Ollama — which used to eat the
    instruction and produce garbage sections."""
    budget = budget or _context_budget()
    if len(transcript) <= budget:
        return transcript
    keep = max(1000, budget - len(TRUNCATION_MARKER) - 2)
    head = int(keep * 0.6)
    tail = keep - head
    log.warning(
        "transcript (%d chars) exceeds the context budget (%d); trimming the middle",
        len(transcript), budget,
    )
    return f"{transcript[:head]}\n{TRUNCATION_MARKER}\n{transcript[-tail:]}"

# Keeps each summary section on-task: many instruct models otherwise prepend a generic
# "This appears to be a transcript of a conversation…" intro to every section.
SUMMARY_SYSTEM = (
    "You write one section of a meeting summary at a time. Output ONLY the content for the "
    "requested section, following its instruction exactly. Do NOT add any introduction, "
    "preamble, heading, or sign-off. Never describe or restate that the input is a transcript "
    "or a conversation, and never begin with phrases like 'This is a transcript' or 'Here is a "
    "summary'. No meta-commentary. Write in the same language the meeting was held in. If the "
    "transcript has nothing relevant to the section, output exactly: None."
)

# Local instruct models routinely ignore the system prompt on long inputs and prepend
# boilerplate anyway. Deterministically strip the known offenders from a section's start.
# Kept narrow on purpose: hedged meta-openers ("This conversation appears to be…") are
# removed, while a confident, content-bearing opener ("This conversation is a meeting
# between Anna and Ben…", as the TL;DR section requests) is left alone.
_PREAMBLE_PATTERNS = [
    re.compile(r"^(?:sure|certainly|of course|okay)[,!.:]\s*", re.IGNORECASE),
    re.compile(r"^here(?:'s| is) (?:the |a |your )?[^.:\n]{0,80}[.:]\s*", re.IGNORECASE),
    re.compile(
        r"^(?:based on|according to) (?:the |this )?(?:provided |given )?"
        r"(?:transcript|conversation|meeting|call|recording)[^,.:\n]{0,40}[,.:]\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^th(?:is|e) (?:conversation|transcript|meeting|call|recording)"
        r"[^.\n]{0,120}?(?:appears|seems) to be[^.\n]*\.\s*",
        re.IGNORECASE,
    ),
]


def clean_section(text: str, title: str = "") -> str:
    """Strip model boilerplate from a summary section: a leading markdown heading that
    just repeats the section title, and known preamble/meta openers."""
    t = (text or "").strip()
    if title:
        first, _, rest = t.partition("\n")
        normalized = re.sub(r"[#*_`:\s]+", " ", first).strip().lower()
        if normalized == title.strip().lower():
            t = rest.strip()
    changed = True
    while changed and t:
        changed = False
        for pattern in _PREAMBLE_PATTERNS:
            stripped = pattern.sub("", t, count=1)
            if stripped != t:
                t = stripped.lstrip()
                changed = True
    return t.strip()


class Pipeline:
    def __init__(self, whisper: FasterWhisperWorker, llm: OpenAICompatProvider) -> None:
        self.whisper = whisper
        self.llm = llm

    def _transcript(self, session: Session, recording_id: int) -> str:
        segs = session.exec(
            select(Segment).where(Segment.recording_id == recording_id).order_by(Segment.start_ts)
        ).all()
        names = speaker_names(session, recording_id)

        def name(seg: Segment) -> str:
            # Distinct fallbacks per unknown speaker id, so two unlabeled speakers
            # don't collapse into one "Speaker" voice in the prompt.
            got = names.get(seg.speaker_id)
            if got:
                return got
            return f"Speaker {seg.speaker_id}" if seg.speaker_id is not None else "Speaker"

        return "\n".join(f"{name(seg)}: {seg.text}" for seg in segs)

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

        fitted = fit_transcript(transcript)
        section_titles = ", ".join(
            str(sec.get("title", "")).strip() for sec in sections_def if sec.get("title")
        )
        produced: list[dict[str, str]] = []
        for section in sections_def:
            title = section.get("title", "")
            source = section.get("prompt", "")
            instruction = render(source, meta)
            if "{{transcript}}" in source:
                # The author placed the transcript themselves — they own the layout.
                prompt = f"SECTION: {title}\nINSTRUCTION: {instruction}" if title else instruction
                if general_context:
                    prompt = f"{general_context}\n\n{prompt}"
            else:
                # Transcript FIRST, instruction LAST: local models weight the end of a
                # long prompt, so a trailing instruction survives where a leading one
                # gets lost behind an hour of transcript.
                parts = [
                    f"MEETING: {meta['title']} ({meta['date']})",
                    f"TRANSCRIPT:\n{fitted}",
                    "---",
                    f'You are writing ONLY the "{title}" section of this meeting\'s summary.'
                    + (
                        f" The full summary has these sections: {section_titles} — leave "
                        "content that belongs to another section to that section."
                        if section_titles
                        else ""
                    ),
                ]
                if general_context:
                    parts.append(f"CONTEXT: {general_context}")
                parts.append(f"INSTRUCTION: {instruction}")
                parts.append(
                    "RULES:\n"
                    "- Start directly with the section content — no introduction, no "
                    "heading, no meta-commentary about the transcript.\n"
                    "- State only what the transcript supports; never invent names, "
                    "numbers, dates, or commitments.\n"
                    "- Write in the language the meeting was held in."
                )
                prompt = "\n\n".join(parts)
            content = await self.llm.generate(prompt, system=SUMMARY_SYSTEM)
            produced.append({"title": title, "content": clean_section(content, title)})

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
        if len(qa_history) > 8000:  # keep runaway chat history from eating the window
            qa_history = "…" + qa_history[-8000:]
        prompt = render(
            tmpl.body,
            {
                "transcript": fit_transcript(transcript),
                "qa_history": qa_history or "(none)",
                "question": question,
            },
        )
        response = await self.llm.generate(prompt)
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
            budget = _cross_context_budget()
            blocks: list[str] = []
            index: list[str] = []
            used = 0
            omitted = 0
            for rec in recs:
                transcript = self._transcript(s, rec.id)  # type: ignore[arg-type]
                if not transcript.strip():
                    continue
                title = rec.title or f"Recording {rec.id}"
                date = rec.started_at.date().isoformat()
                # Every meeting is listed in the index (so "which meeting…" questions can
                # reason over the full set even when a transcript is dropped for length).
                index.append(f"- {date} — {title}")
                block = f"### {title} ({date})\n{transcript}"
                if blocks and used + len(block) > budget:
                    omitted += 1
                    continue
                if len(block) > budget:  # even alone it overflows — trim, don't blow the window
                    block = fit_transcript(block, budget)
                blocks.append(block)
                used += len(block)
            history = s.exec(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at)
            ).all()

        context = "\n\n".join(blocks) or "(no transcripts available)"
        index_text = "\n".join(index) or "(none)"
        hist_text = "\n".join(f"{m.role.upper()}: {m.content}" for m in history)
        if len(hist_text) > 8000:
            hist_text = "…" + hist_text[-8000:]
        prompt = (
            "You are an assistant answering questions across the user's meeting transcripts. "
            "MEETINGS lists every meeting; TRANSCRIPTS holds their content (some may be omitted "
            "for length). Use the transcripts and prior Q&A below; if the answer isn't supported "
            "by them, say so.\n\n"
            f"MEETINGS:\n{index_text}\n\n"
            f"TRANSCRIPTS:\n{context}\n\n"
            f"PRIOR Q&A:\n{hist_text or '(none)'}\n\n"
            f"QUESTION:\n{question}\n\nANSWER:"
        )
        response = await self.llm.generate(prompt)
        answer = response or "(no answer)"
        if omitted:
            answer += f"\n\n_(Note: {omitted} older recording(s) were omitted to fit the context window.)_"
        with Session(engine) as s:
            s.add(ChatMessage(session_id=session_id, role="user", content=question))
            s.add(ChatMessage(session_id=session_id, role="assistant", content=answer))
            s.commit()
        return answer
