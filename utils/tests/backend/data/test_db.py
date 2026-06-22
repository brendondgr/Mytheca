"""Engine factory + session dependency work without a live Postgres."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.db import JSONColumn, get_db, make_engine


def _sqlite_settings(tmp_path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")


def test_make_engine_can_connect(tmp_path):
    engine = make_engine(_sqlite_settings(tmp_path))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1


def test_sessionmaker_yields_working_session(tmp_path):
    engine = make_engine(_sqlite_settings(tmp_path))
    factory = sessionmaker(bind=engine, class_=Session)
    with factory() as session:
        assert session.execute(text("SELECT 1")).scalar() == 1


def test_get_db_yields_and_closes():
    # Bound to the module engine (Postgres URL by default); creating/closing a
    # Session opens no connection, so this needs no live database.
    gen = get_db()
    session = next(gen)
    assert isinstance(session, Session)
    gen.close()  # runs the finally: db.close()


def test_json_column_variant_per_dialect():
    # jsonb on Postgres (indexable later), plain json on SQLite (tests).
    assert "JSONB" in JSONColumn.compile(dialect=postgresql.dialect())
    assert "JSON" in JSONColumn.compile(dialect=sqlite.dialect())
