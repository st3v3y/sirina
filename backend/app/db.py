from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from .config import settings
from .llm.default_templates import _LEGACY_QA_BODIES, QA_TEMPLATE, SUMMARY_TEMPLATES
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
        db_file = settings.db_file
        raise RuntimeError(
            "Database schema is from an older version and is incompatible with this build "
            f"({'; '.join(stale)}). v2 uses a clean schema with no migration — delete the old "
            f"database to reset:\n\n    rm {db_file}*\n    rm -rf {settings.recordings_dir}\n\n"
            "Then restart. (See the README 'clean reset' note.)"
        )


def _add_missing_columns() -> None:
    """Apply small additive column migrations that `create_all` won't do for an
    existing table. SQLite `ADD COLUMN` is cheap and safe; we guard on presence
    so this is idempotent."""
    additive = {
        "summarytemplate": [("general_context", "TEXT")],
        "recording": [
            ("warning", "TEXT"),
            ("pending_trim", "TEXT"),
            ("final_until_s", "REAL"),
            ("live_transcribe", "BOOLEAN DEFAULT 0"),
            ("live_captions", "BOOLEAN DEFAULT 0"),
        ],
        "segment": [("is_draft", "BOOLEAN DEFAULT 0"), ("words", "TEXT")],
        "person": [
            ("is_self", "BOOLEAN DEFAULT 0"),
            ("voiceprint", "TEXT"),
            ("voiceprint_n", "INTEGER DEFAULT 0"),
            ("voiceprint_model", "TEXT"),
        ],
        "speaker": [("embedding", "TEXT"), ("enrolled", "BOOLEAN DEFAULT 0"), ("embedding_model", "TEXT")],
    }
    with engine.connect() as conn:
        tables_present: set[str] = set()
        for table, columns in additive.items():
            existing = {
                row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            }
            if not existing:
                continue  # table not created yet; create_all handles fresh schemas
            tables_present.add(table)
            for name, decl in columns:
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        # Voice fingerprints from before model tagging came from pyannote; SpeakerKit's
        # embeddings live in a different space (same size, so a size check can't tell).
        # Drop the untagged ones once — People keep their names and links and are
        # re-learned from the next renames. Idempotent: tagged prints are untouched.
        if "person" in tables_present:
            conn.exec_driver_sql(
                "UPDATE person SET voiceprint = NULL, voiceprint_n = 0 "
                "WHERE voiceprint IS NOT NULL AND voiceprint_model IS NULL"
            )
        if "speaker" in tables_present:
            conn.exec_driver_sql(
                "UPDATE speaker SET embedding = NULL, enrolled = 0 "
                "WHERE embedding IS NOT NULL AND embedding_model IS NULL"
            )
        conn.commit()


def init_db() -> None:
    # v2 schema is created fresh. There is no migration from the v1 `Meeting`-era
    # database — delete an old `data/transcripts.db` to reset (see README).
    SQLModel.metadata.create_all(engine)
    _add_missing_columns()
    _assert_schema_current()
    with Session(engine) as session:
        existing = session.exec(select(SummaryTemplate)).all()
        if not existing:
            for t in SUMMARY_TEMPLATES:
                session.add(SummaryTemplate(**t))
        else:
            # Refresh built-in templates' sections from code so default-template tweaks
            # (new sections, dropped {{transcript}} clutter) reach existing installs.
            # User-created templates and the user's chosen default are left untouched.
            by_name = {t.name: t for t in existing}
            for t in SUMMARY_TEMPLATES:
                cur = by_name.get(t["name"])
                if cur is not None and cur.builtin:
                    cur.sections = t["sections"]
                    session.add(cur)
        qa = session.exec(select(PromptTemplate)).first()
        if qa is None:
            session.add(PromptTemplate(**QA_TEMPLATE))
        elif qa.body.strip() in {b.strip() for b in _LEGACY_QA_BODIES}:
            # The stored Q&A prompt is an unmodified previous default — upgrade it.
            # A user-customised prompt never matches and is left untouched.
            qa.body = QA_TEMPLATE["body"]
            session.add(qa)
        session.commit()
        _backfill_self_person(session)


def _backfill_self_person(session: Session) -> None:
    """Bind existing "You" speakers (from recordings made before the self-Person existed)
    to the singleton self-Person, so the app user appears in People for past recordings."""
    from .models import Speaker
    from .speakers import SELF_LABEL, get_or_create_self_person

    orphan_you = session.exec(
        select(Speaker).where(Speaker.label == SELF_LABEL, Speaker.person_id == None)  # noqa: E711
    ).all()
    if not orphan_you:
        return
    self_id = get_or_create_self_person(session).id
    for sp in orphan_you:
        sp.person_id = self_id
        session.add(sp)
    session.commit()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
