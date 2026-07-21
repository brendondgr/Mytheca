"""Qdrant client factory — the Hybrid RAG vector store.

The lazy, *graceful* client for Mytheca's vector store, mirroring
``app/core/neo4j.py``:

- the **container** is owned by ``app.py`` (brought up with Postgres/Redis/Neo4j);
- the **client** is built lazily and cached as a process singleton;
- everything degrades gracefully. When ``QDRANT_URL`` is unset, ``get_client``
  returns ``None`` and ``ping`` returns ``False`` without raising, so CRUD and the
  no-Docker ``pytest`` path run with no Qdrant. The store/indexer gate on this.

Tests inject ``QdrantClient(":memory:")`` directly into the store helpers (local
in-process mode — no server), so they never touch this module's singleton.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import get_settings

if TYPE_CHECKING:
    from qdrant_client import QdrantClient

# Process-wide singleton; ``close_client`` resets it (app shutdown / tests).
_client: QdrantClient | None = None


def is_enabled() -> bool:
    """True when a Qdrant URL is configured (cheap — opens no connection)."""
    return get_settings().qdrant_configured


def build_client() -> QdrantClient:
    """Construct a fresh client from settings. Injection seam for tests."""
    from qdrant_client import QdrantClient

    return QdrantClient(url=get_settings().qdrant_url)


def get_client() -> QdrantClient | None:
    """Return the shared client, or ``None`` when Qdrant is not configured.

    Lazily built on first use and cached. Returning ``None`` (rather than raising)
    lets the indexer/retriever no-op when the store is absent without each caller
    wrapping construction in try/except.
    """
    global _client
    if not is_enabled():
        return None
    if _client is None:
        _client = build_client()
    return _client


def close_client() -> None:
    """Close and forget the shared client (idempotent; never raises)."""
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
        finally:
            _client = None


def ping() -> bool:
    """Return True if Qdrant answers; never raises (used by preflight)."""
    try:
        client = get_client()
        if client is None:
            return False
        client.get_collections()
        return True
    except Exception:
        return False
