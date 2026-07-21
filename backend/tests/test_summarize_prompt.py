"""Verify summarize() auto-injects the transcript once and prepends general context."""
import app.pipeline as pipeline_mod
from app.models import Recording, Segment, Speaker, SummaryTemplate
from app.pipeline import Pipeline


class FakeLLM:
    def __init__(self):
        self.prompts = []

    async def generate(self, prompt, *, model=None, system=None):
        self.prompts.append(prompt)
        return "ok"


def _seed(session):
    rec = Recording(status="ready", title="Standup")
    session.add(rec)
    session.commit()
    session.refresh(rec)
    sp = Speaker(recording_id=rec.id, label="You")
    session.add(sp)
    session.commit()
    session.refresh(sp)
    session.add(Segment(recording_id=rec.id, speaker_id=sp.id, start_ts=0, end_ts=2, text="hello world"))
    session.commit()
    return rec.id


async def _run(engine, template):
    import asyncio

    from sqlmodel import Session

    with Session(engine) as s:
        rid = _seed(s)
        s.add(template)
        s.commit()
        s.refresh(template)
        tid = template.id

    # Point the pipeline's engine at our in-memory db.
    orig = pipeline_mod.engine
    pipeline_mod.engine = engine
    try:
        fake = FakeLLM()
        p = Pipeline(whisper=None, llm=fake)  # type: ignore[arg-type]
        await p.summarize(recording_id=rid, template_id=tid)
        return fake.prompts
    finally:
        pipeline_mod.engine = orig


def _engine():
    from sqlmodel import SQLModel, create_engine

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return eng


def test_transcript_auto_appended_when_missing():
    import asyncio

    eng = _engine()
    tmpl = SummaryTemplate(name="t", sections=[{"title": "S", "prompt": "Summarise."}])
    prompts = asyncio.run(_run(eng, tmpl))
    assert len(prompts) == 1
    p = prompts[0]
    assert "TRANSCRIPT:" in p
    assert "hello world" in p
    # exactly one transcript copy
    assert p.count("hello world") == 1


def test_no_double_transcript_when_placeholder_present():
    import asyncio

    eng = _engine()
    tmpl = SummaryTemplate(name="t", sections=[{"title": "S", "prompt": "Summarise:\n{{transcript}}"}])
    prompts = asyncio.run(_run(eng, tmpl))
    assert prompts[0].count("hello world") == 1


def test_general_context_included_before_instruction():
    import asyncio

    eng = _engine()
    tmpl = SummaryTemplate(
        name="t",
        general_context="You are a terse assistant.",
        sections=[{"title": "S", "prompt": "Summarise."}],
    )
    prompts = asyncio.run(_run(eng, tmpl))
    p = prompts[0]
    assert "CONTEXT: You are a terse assistant." in p
    # Transcript first, framing+instruction after (local models weight the prompt tail).
    assert p.index("TRANSCRIPT:") < p.index("CONTEXT:") < p.index("INSTRUCTION: Summarise.")


def test_instruction_follows_transcript():
    import asyncio

    eng = _engine()
    tmpl = SummaryTemplate(name="t", sections=[{"title": "S", "prompt": "Summarise."}])
    prompts = asyncio.run(_run(eng, tmpl))
    p = prompts[0]
    assert p.index("TRANSCRIPT:") < p.index("INSTRUCTION: Summarise.")
    assert "RULES:" in p
