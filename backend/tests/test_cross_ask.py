"""Tests for cross-recording chat: context building, newest-first, omission note."""
import asyncio

import app.pipeline as pipeline_mod
from app.models import ChatMessage, ChatSession, Recording, Segment, Speaker
from app.pipeline import Pipeline
from sqlmodel import Session, SQLModel, create_engine, select


class FakeLLM:
    def __init__(self):
        self.prompts = []

    async def generate(self, prompt, *, model=None, system=None):
        self.prompts.append(prompt)
        return "answer"


def _engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return eng


def _add_recording(session, title, text, started_at):
    rec = Recording(status="ready", title=title, started_at=started_at)
    session.add(rec)
    session.commit()
    session.refresh(rec)
    sp = Speaker(recording_id=rec.id, label="You")
    session.add(sp)
    session.commit()
    session.refresh(sp)
    session.add(Segment(recording_id=rec.id, speaker_id=sp.id, start_ts=0, end_ts=1, text=text))
    session.commit()
    return rec.id


def _run(engine, session_id, question):
    orig = pipeline_mod.engine
    pipeline_mod.engine = engine
    try:
        fake = FakeLLM()
        p = Pipeline(whisper=None, llm=fake)  # type: ignore[arg-type]
        answer = asyncio.run(p.cross_ask(session_id=session_id, question=question))
        return answer, fake.prompts
    finally:
        pipeline_mod.engine = orig


def test_context_includes_all_transcripts():
    from datetime import datetime, timezone

    eng = _engine()
    with Session(eng) as s:
        _add_recording(s, "Mon", "alpha topic", datetime(2026, 1, 1, tzinfo=timezone.utc))
        _add_recording(s, "Tue", "beta topic", datetime(2026, 1, 2, tzinfo=timezone.utc))
        sess = ChatSession()
        s.add(sess)
        s.commit()
        s.refresh(sess)
        sid = sess.id

    answer, prompts = _run(eng, sid, "what happened?")
    assert "alpha topic" in prompts[0]
    assert "beta topic" in prompts[0]
    # newest-first: Tue appears before Mon
    assert prompts[0].index("beta topic") < prompts[0].index("alpha topic")
    assert answer == "answer"  # no omission note when nothing dropped

    # The turn was persisted.
    with Session(eng) as s:
        msgs = s.exec(select(ChatMessage).where(ChatMessage.session_id == sid)).all()
        assert [m.role for m in msgs] == ["user", "assistant"]


def test_omission_note_when_over_budget(monkeypatch):
    from datetime import datetime, timezone

    # Force a tiny context budget so the older recording is dropped (the real budget has
    # a 4000-char floor, so patch the accessor rather than a setting).
    monkeypatch.setattr(pipeline_mod, "_cross_context_budget", lambda: 50)
    eng = _engine()
    with Session(eng) as s:
        _add_recording(s, "Old", "x" * 100, datetime(2026, 1, 1, tzinfo=timezone.utc))
        _add_recording(s, "New", "y" * 100, datetime(2026, 1, 2, tzinfo=timezone.utc))
        sess = ChatSession()
        s.add(sess)
        s.commit()
        s.refresh(sess)
        sid = sess.id

    answer, prompts = _run(eng, sid, "q")
    assert "omitted" in answer.lower()
    # The newest recording is kept; the older one is dropped.
    assert "y" * 100 in prompts[0]
    assert "x" * 100 not in prompts[0]
