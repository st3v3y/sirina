from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Meeting(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str | None = None
    guild_id: str
    channel_id: str
    started_at: datetime = Field(default_factory=_utcnow)
    ended_at: datetime | None = None
    status: str = Field(default="recording")  # recording | ended | failed
    source: str = Field(default="discord")  # discord | local


class Segment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meeting.id", index=True)
    discord_user_id: str
    username: str
    start_ts: float
    end_ts: float
    text: str


class Summary(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meeting.id", index=True)
    kind: str  # live_aspect | full | qa_answer
    template_id: int | None = Field(default=None, foreign_key="prompttemplate.id")
    content: str
    created_at: datetime = Field(default_factory=_utcnow)


class PromptTemplate(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    kind: str  # summary | aspects | qa
    body: str
    is_default: bool = False


class QAMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meeting.id", index=True)
    role: str  # user | assistant
    content: str
    created_at: datetime = Field(default_factory=_utcnow)
