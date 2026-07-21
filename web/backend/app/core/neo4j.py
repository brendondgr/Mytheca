"""Neo4j driver factory and health helper — the Story Graph substrate.

Mytheca keeps **one** knowledge graph, the Story Graph, on Neo4j (see
``Documents/Plans/5.4_story-graph-structure-prep.md`` §6). This module is the
lazy, *graceful* client for it, mirroring ``app/core/redis.py``:

- the **container** is owned by ``app.py`` (brought up with Postgres/Redis);
- the **driver** connects lazily — only when a Scenario is loaded or a Character/
  Setting is written — and is a long-lived, pooled singleton;
- everything degrades gracefully. When ``NEO4J_URI`` is unset, or the server is
  down, ``get_driver`` returns ``None`` and ``ping`` returns ``False`` without
  raising, so CRUD and the no-Docker ``pytest`` path run with no Neo4j.

Read vs. write sessions are explicit. ``read_session`` opens a transaction in
**READ** access mode (Neo4j rejects writes server-side — the mechanical hot-path
purity of §7.4); ``write_session`` opens **WRITE** mode for the authoring path.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from neo4j import READ_ACCESS, WRITE_ACCESS, Driver, GraphDatabase, Session

from app.core.config import get_settings

# Process-wide singleton. The Neo4j driver owns a connection pool and is meant to
# be built once and reused; ``close_driver`` resets it (used by app shutdown/tests).
_driver: Driver | None = None


def is_enabled() -> bool:
    """True when a Neo4j URI is configured (cheap — opens no connection)."""
    return get_settings().neo4j_configured


def build_driver() -> Driver:
    """Construct a fresh driver from settings. Injection seam for tests."""
    settings = get_settings()
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


def get_driver() -> Driver | None:
    """Return the shared driver, or ``None`` when Neo4j is not configured.

    Lazily built on first use and cached for the process. Returning ``None``
    (rather than raising) lets the writer/reader no-op when the substrate is
    absent without each caller wrapping construction in try/except.
    """
    global _driver
    if not is_enabled():
        return None
    if _driver is None:
        _driver = build_driver()
    return _driver


def close_driver() -> None:
    """Close and forget the shared driver (idempotent; never raises)."""
    global _driver
    if _driver is not None:
        try:
            _driver.close()
        except Exception:
            pass
        finally:
            _driver = None


def ping() -> bool:
    """Return True if Neo4j answers connectivity; never raises (used by preflight)."""
    try:
        driver = get_driver()
        if driver is None:
            return False
        driver.verify_connectivity()
        return True
    except Exception:
        return False


@contextmanager
def read_session(**kwargs: Any) -> Iterator[Session]:
    """A **read-only** session (Neo4j READ access mode — §7.4 hot-path purity).

    Only call when ``is_enabled()`` / ``get_driver()`` is truthy; the best-effort
    wrappers in ``services/graph_reader.py`` gate on that first.
    """
    driver = get_driver()
    if driver is None:  # pragma: no cover - guarded by callers
        raise RuntimeError("Neo4j is not configured; gate on is_enabled() first.")
    session = driver.session(default_access_mode=READ_ACCESS, **kwargs)
    try:
        yield session
    finally:
        session.close()


@contextmanager
def write_session(**kwargs: Any) -> Iterator[Session]:
    """A write session (WRITE access mode) for the authoring/cold paths."""
    driver = get_driver()
    if driver is None:  # pragma: no cover - guarded by callers
        raise RuntimeError("Neo4j is not configured; gate on is_enabled() first.")
    session = driver.session(default_access_mode=WRITE_ACCESS, **kwargs)
    try:
        yield session
    finally:
        session.close()
