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


@pytest.fixture(autouse=True)
def _redis_disabled_by_default(monkeypatch) -> Iterator[None]:
    """Run the suite with the live turn buffer / interior state off (no real Redis).

    Blanking ``REDIS_URL`` makes ``Settings.redis_configured`` false, so the
    best-effort ``app.memory`` helpers no-op — the turn loop still runs and persists
    to (SQLite) Postgres. Mirrors ``_graph_disabled_by_default`` / ``_rag_offline``.
    Tests that exercise the buffer inject a fake client explicitly.
    """
    from app.core.redis import get_redis

    monkeypatch.setenv("REDIS_URL", "")
    config.get_settings.cache_clear()
    get_redis.cache_clear()
    yield
    config.get_settings.cache_clear()
    get_redis.cache_clear()


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


@pytest.fixture
def per_speaker_scenes(monkeypatch):
    """Pin `sceneFlow` to `"voiced"` for a module that tests the per-speaker writer.

    Continuous prose became the default on 2026-08-24, and it does not merely produce the
    same beats through one call: it bypasses the per-speaker prompt entirely — the register
    directive, the voice samples, the relationship note, the carried disposition and the
    owed-requirements tail all live in `character_turn_agent._build_user_prompt`, and a
    continuous script never builds one.

    So a module asserting on any of that is a **voiced-path** module, and this makes it say
    so. The alternative — quietly adding `sceneFlow: "voiced"` to forty scenario fixtures —
    would leave a reader unable to tell which tests were deliberately pinned and which had
    simply never been revisited.

    Used as `pytestmark = pytest.mark.usefixtures("per_speaker_scenes")` at module level.
    """
    from app.services import turn_settings

    monkeypatch.setattr(turn_settings, "DEFAULT_SCENE_FLOW", "voiced")
