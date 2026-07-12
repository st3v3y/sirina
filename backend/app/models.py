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
    warning: str | None = None  # non-fatal capture issue, e.g. a source track ended short
    # When set (JSON: {"leading_s": x, "trailing_s": y}), the recording was stopped with a
    # long stretch of leading/trailing silence and is HELD awaiting the user's trim decision
    # (not yet enqueued for transcription). Cleared once they choose Trim or Keep.
    pending_trim: str | None = None


class Person(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    # The app user ("You"): a singleton Person auto-linked to every recording's mic
    # speaker. Renaming the "You" speaker renames this Person (it is never duplicated).
    is_self: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow)


class Speaker(SQLModel, table=True):
    """A per-recording speaker. `label` is the default ("You"/"Others"/"Speaker 1");
    when linked to a Person, the Person's name is the display name."""

    id: int | None = Field(default=None, primary_key=True)
    recording_id: int = Field(foreign_key="recording.id", index=True)
    label: str
    person_id: int | None = Field(default=None, foreign_key="person.id")
    color: str | None = None


class Segment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    recording_id: int = Field(foreign_key="recording.id", index=True)
    speaker_id: int | None = Field(default=None, foreign_key="speaker.id", index=True)
    start_ts: float
    end_ts: float
    text: str


class SummaryTemplate(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    # Optional free-text framing prepended to every section prompt at summarize time.
    general_context: str | None = None
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


class Tag(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    color: str | None = None


class RecordingTag(SQLModel, table=True):
    recording_id: int = Field(foreign_key="recording.id", primary_key=True, index=True)
    tag_id: int = Field(foreign_key="tag.id", primary_key=True, index=True)


class ChatSession(SQLModel, table=True):
    """A cross-recording AI chat session: questions answered over all transcripts."""

    id: int | None = Field(default=None, primary_key=True)
    title: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class ChatMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="chatsession.id", index=True)
    role: str  # user | assistant
    content: str
    created_at: datetime = Field(default_factory=_utcnow)


class Setting(SQLModel, table=True):
    """A persisted user override for a single config key. Layered on top of the
    built-in defaults and `.env` at startup (defaults → .env → these rows). Values
    are stored as text and coerced to the field's type by the settings registry."""

    key: str = Field(primary_key=True)
    value: str = ""
