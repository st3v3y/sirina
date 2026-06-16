from collections.abc import Iterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from .config import settings
from .llm.default_templates import QA_TEMPLATE, SUMMARY_TEMPLATES
from .models import PromptTemplate, SummaryTemplate

engine = create_engine(
    settings.db_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


@event.listens_for(Engine, "connect")
def _enable_sqlite_wal(dbapi_conn, _):  # type: ignore[no-untyped-def]
    try:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()
    except Exception:
        pass


def init_db() -> None:
    # v2 schema is created fresh. There is no migration from the v1 `Meeting`-era
    # database — delete an old `data/transcripts.db` to reset (see README).
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        if session.exec(select(SummaryTemplate)).first() is None:
            for t in SUMMARY_TEMPLATES:
                session.add(SummaryTemplate(**t))
        if session.exec(select(PromptTemplate)).first() is None:
            session.add(PromptTemplate(**QA_TEMPLATE))
        session.commit()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
