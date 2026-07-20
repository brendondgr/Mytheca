"""Qdrant collection + upsert/search/delete (brief §4).

One ``mytheca_lore`` collection holds every entry as a point with two named
vectors — ``dense`` (bge-large) and ``bm25`` (sparse/lexical) — plus a payload
carrying the front-matter filter fields, the body text (for LLM context), and a
``content_hash`` for idempotent re-indexing. Every point is tagged with its
``storyline_id`` so retrieval filters a world to its own corpus.

Functions take an explicit ``client`` so tests drive them with an in-process
``QdrantClient(":memory:")``; the runtime client comes from ``app.core.qdrant``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from qdrant_client import models

from app.core.config import get_settings
from app.rag.const import POINT_NAMESPACE
from app.rag.embedder import SparseVector

if TYPE_CHECKING:
    from qdrant_client import QdrantClient

DENSE = "dense"
SPARSE = "bm25"


@dataclass(frozen=True)
class StoreHit:
    """A single retrieval hit: the Mytheca entry id, the channel score, the payload."""

    entry_id: str
    score: float
    payload: dict[str, Any]


def point_id(entity_type: str, entity_id: str) -> str:
    """Deterministic Qdrant point id (uuid5) for an entity's entry.

    Namespaced by ``entity_type`` so a character and a context document can never
    collide, and stable across runs so re-indexing upserts in place.
    """
    return str(uuid.uuid5(POINT_NAMESPACE, f"{entity_type}:{entity_id}"))


def _collection(name: str | None) -> str:
    return name or get_settings().qdrant_collection


def ensure_collection(client: QdrantClient, *, collection: str | None = None, dim: int | None = None) -> None:
    """Create the collection (named dense + sparse vectors) if absent. Idempotent."""
    name = _collection(collection)
    if client.collection_exists(name):
        return
    size = dim or get_settings().embed_dim
    client.create_collection(
        collection_name=name,
        vectors_config={DENSE: models.VectorParams(size=size, distance=models.Distance.COSINE)},
        sparse_vectors_config={SPARSE: models.SparseVectorParams()},
    )


def storyline_filter(storyline_id: str | None, extra: list[models.Condition] | None = None) -> models.Filter | None:
    """Build a payload filter scoping to one storyline (+ optional extra conditions)."""
    must: list[models.Condition] = []
    if storyline_id:
        must.append(models.FieldCondition(key="storyline_id", match=models.MatchValue(value=storyline_id)))
    if extra:
        must.extend(extra)
    return models.Filter(must=must) if must else None


def upsert_entry(
    client: QdrantClient,
    *,
    entity_type: str,
    entity_id: str,
    dense: list[float],
    sparse: SparseVector,
    payload: dict[str, Any],
    collection: str | None = None,
) -> str:
    """Upsert one entry's point (keyed by its deterministic point id). Returns the id."""
    name = _collection(collection)
    pid = point_id(entity_type, entity_id)
    client.upsert(
        collection_name=name,
        points=[
            models.PointStruct(
                id=pid,
                vector={
                    DENSE: dense,
                    SPARSE: models.SparseVector(indices=sparse.indices, values=sparse.values),
                },
                payload=payload,
            )
        ],
    )
    return pid


def delete_entry(client: QdrantClient, entity_type: str, entity_id: str, *, collection: str | None = None) -> None:
    """Remove the point owned by an entity (by its deterministic point id)."""
    client.delete(
        collection_name=_collection(collection),
        points_selector=models.PointIdsList(points=[point_id(entity_type, entity_id)]),
    )


def delete_by_filter(client: QdrantClient, flt: models.Filter, *, collection: str | None = None) -> None:
    """Remove every point matching ``flt`` (e.g. a whole storyline's corpus)."""
    client.delete(collection_name=_collection(collection), points_selector=models.FilterSelector(filter=flt))


def _hits(points: list[Any]) -> list[StoreHit]:
    return [
        StoreHit(entry_id=str((p.payload or {}).get("entry_id", p.id)), score=float(p.score), payload=p.payload or {})
        for p in points
    ]


def dense_search(
    client: QdrantClient, dense: list[float], *, k: int, flt: models.Filter | None = None, collection: str | None = None
) -> list[StoreHit]:
    res = client.query_points(
        collection_name=_collection(collection), query=dense, using=DENSE, limit=k,
        query_filter=flt, with_payload=True,
    )
    return _hits(res.points)


def sparse_search(
    client: QdrantClient, sparse: SparseVector, *, k: int, flt: models.Filter | None = None, collection: str | None = None
) -> list[StoreHit]:
    res = client.query_points(
        collection_name=_collection(collection),
        query=models.SparseVector(indices=sparse.indices, values=sparse.values),
        using=SPARSE, limit=k, query_filter=flt, with_payload=True,
    )
    return _hits(res.points)


def count(client: QdrantClient, *, flt: models.Filter | None = None, collection: str | None = None) -> int:
    """Number of points (optionally within a filter) — used by the RAG status surface."""
    return client.count(collection_name=_collection(collection), count_filter=flt).count


def existing_content_hash(
    client: QdrantClient, entity_type: str, entity_id: str, *, collection: str | None = None
) -> str | None:
    """Return the stored ``content_hash`` of an entity's point, or ``None``.

    Lets the indexer skip re-embedding an unchanged entry. Best-effort — a missing
    collection/point or any client error reads as "no prior hash" (→ re-index)."""
    try:
        got = client.retrieve(
            collection_name=_collection(collection),
            ids=[point_id(entity_type, entity_id)],
            with_payload=True,
        )
    except Exception:
        return None
    if not got:
        return None
    return (got[0].payload or {}).get("content_hash")
