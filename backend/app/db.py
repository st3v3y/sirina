from collections.abc import Iterator
from pathlib import Path

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


# Tables that changed shape across schema generations, with a column that only
# exists in the current (v2) schema. `create_all` never alters an existing table,
# so a table left over from an older schema would silently keep its old columns
# and 500 at query time — we detect that here and fail fast with a clear message.
_REQUIRED_COLUMNS = {
    "segment": "recording_id",
    "summary": "sections",
    "qamessage": "recording_id",
}


def _assert_schema_current() -> None:
    with engine.connect() as conn:

        def columns(table: str) -> set[str]:
            return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()}

        stale: list[str] = []
        # A leftover v1 `meeting` table is a definitive marker of an old database.
        if columns("meeting"):
            stale.append("legacy `meeting` table present")
        for table, required in _REQUIRED_COLUMNS.items():
            cols = columns(table)
            if cols and required not in cols:
                stale.append(f"`{table}` is missing column `{required}`")

    if stale:
        db_file = Path(settings.db_path).resolve()
        raise RuntimeError(
            "Database schema is from an older version and is incompatible with this build "
            f"({'; '.join(stale)}). v2 uses a clean schema with no migration — delete the old "
            f"database to reset:\n\n    rm {db_file}*\n    rm -rf {db_file.parent / 'recordings'}\n\n"
            "Then restart. (See the README 'clean reset' note.)"
        )


def _add_missing_columns() -> None:
    """Apply small additive column migrations that `create_all` won't do for an
    existing table. SQLite `ADD COLUMN` is cheap and safe; we guard on presence
    so this is idempotent."""
    additive = {
        "summarytemplate": [("general_context", "TEXT")],
    }
    with engine.connect() as conn:
        for table, columns in additive.items():
            existing = {
                row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            }
            if not existing:
                continue  # table not created yet; create_all handles fresh schemas
            for name, decl in columns:
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        conn.commit()


def init_db() -> None:
    # v2 schema is created fresh. There is no migration from the v1 `Meeting`-era
    # database — delete an old `data/transcripts.db` to reset (see README).
    SQLModel.metadata.create_all(engine)
    _add_missing_columns()
    _assert_schema_current()
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
