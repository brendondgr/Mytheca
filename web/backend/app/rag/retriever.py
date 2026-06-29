"""Hybrid retrieval — dense + BM25 fused with RRF, storyline-scoped (brief §5).

The request flow: query → dense (bge) + sparse (bm25) in parallel over the
storyline's corpus → RRF fusion (ranks, never the incompatible cosine/BM25
scales) → top-N records for the LLM. An optional metadata pre-filter (brief §5.3)
narrows by a named setting; it is **off by default** in the agent path (the corpus
is already storyline-scoped and small) and applied with a graceful fallback so it
can never starve a query to zero hits. Best-effort: no store → empty result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from qdrant_client import models

from app.core import qdrant
from app.core.errors import APIError
from app.rag import store
from app.rag.const import CONTEXT_N, DENSE_K, FUSE_TOP_N, RRF_K, SPARSE_K
from app.rag.embedder import Embedder, get_embedder

if TYPE_CHECKING:
    from qdrant_client import QdrantClient
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class RetrievedEntry:
    """A retrieved lore entry: id, display name, type, body text, fused score."""

    entry_id: str
    name: str
    type: str
    body: str
    score: float


def rrf_fuse(
    dense_hits: list[store.StoreHit],
    sparse_hits: list[store.StoreHit],
    *,
    k: int = RRF_K,
    top_n: int = FUSE_TOP_N,
) -> list[tuple[str, float]]:
    """Reciprocal-rank fusion of two ranked lists (brief §5.2)."""
    scores: dict[str, float] = {}
    for rank, hit in enumerate(dense_hits):
        scores[hit.entry_id] = scores.get(hit.entry_id, 0.0) + 1.0 / (k + rank)
    for rank, hit in enumerate(sparse_hits):
        scores[hit.entry_id] = scores.get(hit.entry_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]


def build_filter(db: Session, storyline_id: str, query: str) -> list[models.Condition] | None:
    """Match the query against the world's known setting names → location conditions.

    Conservative pre-filter (brief §5.3): only fires when the query literally names
    a setting. Returns ``None`` when nothing matches. Applied with a fallback in
    ``retrieve`` so it never over-narrows to an empty result."""
    from app.services import crud  # local import avoids a retriever ↔ crud cycle

    try:
        settings = crud.list_settings(db, storyline_id)
    except APIError:
        return None
    ql = query.lower()
    conds: list[models.Condition] = [
        models.FieldCondition(key="location", match=models.MatchValue(value=s.name))
        for s in settings
        if s.name and s.name.lower() in ql
    ]
    return conds or None


def _search(client: QdrantClient, qv: list[float], sv, flt: models.Filter | None):
    dense = store.dense_search(client, qv, k=DENSE_K, flt=flt)
    sparse = store.sparse_search(client, sv, k=SPARSE_K, flt=flt)
    return dense, sparse


def retrieve(
    db: Session,
    storyline_id: str,
    query: str,
    *,
    k: int = CONTEXT_N,
    prefilter: bool = False,
    client: QdrantClient | None = None,
    embedder: Embedder | None = None,
) -> list[RetrievedEntry]:
    """Return the top-``k`` entries for ``query`` within ``storyline_id``'s corpus."""
    query = (query or "").strip()
    if not query:
        return []
    client = client or qdrant.get_client()
    if client is None:
        return []
    embedder = embedder or get_embedder()
    qv = embedder.embed_query(query)
    sv = embedder.embed_sparse_query(query)

    conds = build_filter(db, storyline_id, query) if prefilter else None
    flt = store.storyline_filter(storyline_id, extra=conds)
    try:
        dense, sparse = _search(client, qv, sv, flt)
        fused = rrf_fuse(dense, sparse)
        if not fused and conds:  # pre-filter over-narrowed → retry storyline-only
            flt = store.storyline_filter(storyline_id)
            dense, sparse = _search(client, qv, sv, flt)
            fused = rrf_fuse(dense, sparse)
    except Exception:  # best-effort — a store hiccup never breaks the caller
        return []

    payloads = {h.entry_id: h.payload for h in [*sparse, *dense]}
    out: list[RetrievedEntry] = []
    for entry_id, score in fused[:k]:
        p = payloads.get(entry_id, {})
        out.append(
            RetrievedEntry(
                entry_id=entry_id,
                name=str(p.get("name", "")),
                type=str(p.get("type", "")),
                body=str(p.get("body", "")),
                score=score,
            )
        )
    return out
