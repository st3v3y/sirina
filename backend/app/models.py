from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Recording(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime = Field(default_factory=_utcnow)
    ended_at: datetime | None = None
    duration_s: float | None = None
    status: str = Field(default="recording")  # recording | processing | ready | failed
    language: str | None = None
    mic_path: str | None = None
    system_path: str | None = None
    audio_path: str | None = None  # mixed/primary track used for playback + transcription
    error: str | None = None


class Segment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    recording_id: int = Field(foreign_key="recording.id", index=True)
    speaker_label: str = "Speaker"  # populated by transcription/diarization later
    start_ts: float
    end_ts: float
    text: str


class SummaryTemplate(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    # ordered sections: [{ "title": str, "prompt": str }, ...]
    sections: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    is_default: bool = False
    builtin: bool = False  # seeded in code; not user-deletable


class Summary(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    recording_id: int = Field(foreign_key="recording.id", index=True)
    template_id: int | None = Field(default=None, foreign_key="summarytemplate.id")
    # produced sections: [{ "title": str, "content": str }, ...]
    sections: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)


class PromptTemplate(SQLModel, table=True):
    """The Q&A prompt (single-prompt). Summaries use SummaryTemplate."""

    id: int | None = Field(default=None, primary_key=True)
    name: str
    body: str
    is_default: bool = False


class QAMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    recording_id: int = Field(foreign_key="recording.id", index=True)
    role: str  # user | assistant
    content: str
    created_at: datetime = Field(default_factory=_utcnow)
