"""Shared backend test fixtures.

The suite runs entirely on an in-memory SQLite database (StaticPool so every
connection sees the same in-memory db) — no Postgres or Docker required. Importing
``app.models`` registers every table on ``Base.metadata``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — registers all tables on Base.metadata
from app.core.db import Base, get_db
from app.main import create_app


@pytest.fixture
def engine() -> Iterator[Engine]:
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        Base.metadata.drop_all(eng)
        eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
    with factory() as session:
        yield session


@pytest.fixture
def client(engine: Engine) -> TestClient:
    """A TestClient whose get_db is overridden to the in-memory SQLite engine.

    Instantiated without ``with`` so the app lifespan (which talks to Postgres in
    later phases) does not run during tests.
    """
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)

    def override_get_db() -> Iterator[Session]:
        with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture
def storyline_id(client: TestClient) -> str:
    """Create and return a storyline id for the scoped CRUD tests."""
    return client.post(
        "/api/storylines", json={"id": "embergate", "title": "Embergate", "genre": "Maritime"}
    ).json()["id"]
