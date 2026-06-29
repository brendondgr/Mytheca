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
from app.core import config
from app.core.db import Base, get_db
from app.main import create_app


@pytest.fixture(autouse=True)
def _graph_disabled_by_default(monkeypatch) -> Iterator[None]:
    """Run the suite with the Story Graph disabled (no real Neo4j).

    The default ``NEO4J_URI`` points at the local container, so without this the
    best-effort graph sync in CRUD would attempt a real connection during tests.
    Blanking it makes ``neo4j.is_enabled()`` false everywhere — graph writes/reads
    no-op (the graceful posture). Tests that exercise the graph enable it
    explicitly with an injected fake driver/session.
    """
    monkeypatch.setenv("NEO4J_URI", "")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _rag_offline(monkeypatch) -> Iterator[None]:
    """Run the suite with the real embedding model + Qdrant off.

    ``EMBED_PROVIDER=hash`` forces the deterministic feature-hashing embedder so no
    ~1.3 GB ONNX model is ever downloaded; blanking ``QDRANT_URL`` makes the vector
    store best-effort-disabled. Tests that exercise retrieval inject an in-memory
    ``QdrantClient(":memory:")`` explicitly. Mirrors ``_graph_disabled_by_default``.
    """
    from app.rag.embedder import get_embedder

    monkeypatch.setenv("EMBED_PROVIDER", "hash")
    monkeypatch.setenv("QDRANT_URL", "")
    config.get_settings.cache_clear()
    get_embedder.cache_clear()
    yield
    config.get_settings.cache_clear()
    get_embedder.cache_clear()


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
