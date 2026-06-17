"""Verify the additive `general_context` column migration is applied and idempotent."""
import app.db as db_mod
from sqlmodel import create_engine


def _cols(engine, table):
    with engine.connect() as conn:
        return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()}


def test_adds_missing_general_context(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    # Simulate an older DB: summarytemplate without general_context.
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE summarytemplate (id INTEGER PRIMARY KEY, name TEXT, sections JSON)"
        )
    monkeypatch.setattr(db_mod, "engine", engine)

    assert "general_context" not in _cols(engine, "summarytemplate")
    db_mod._add_missing_columns()
    assert "general_context" in _cols(engine, "summarytemplate")
    # Idempotent: running again does not error or duplicate.
    db_mod._add_missing_columns()
    assert "general_context" in _cols(engine, "summarytemplate")


def test_no_table_is_skipped(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_mod, "engine", engine)
    # No tables exist yet — must not raise.
    db_mod._add_missing_columns()
