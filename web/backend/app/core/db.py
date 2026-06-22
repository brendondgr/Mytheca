"""Database engine, session factory, and the declarative ``Base``.

Synchronous SQLAlchemy 2.0 over psycopg3. Route handlers are plain ``def`` so
FastAPI runs them in a threadpool (see ``docs/architecture.md``). Models use the
portable ``JSONColumn`` type and Python-side defaults so the *same* metadata
creates on Postgres (the running app) and SQLite (the test suite) without
dialect-specific server defaults.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import Settings, get_settings


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


# Portable JSON column: ``jsonb`` on Postgres (indexable later), plain ``json``
# on SQLite so the test suite can round-trip the same models.
JSONColumn = JSON().with_variant(JSONB, "postgresql")


def make_engine(settings: Settings | None = None) -> Engine:
    """Build a SQLAlchemy engine for the configured database.

    ``create_engine`` is lazy — no connection is opened until first use — so
    importing this module never requires a live Postgres.
    """
    settings = settings or get_settings()
    connect_args: dict[str, object] = {}
    if settings.is_sqlite:
        # SQLite must allow cross-thread use (FastAPI threadpool / tests).
        connect_args["check_same_thread"] = False
    return create_engine(
        settings.database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )


# Module-level engine + session factory bound to the configured database.
engine: Engine = make_engine()
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yield a session and always close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
