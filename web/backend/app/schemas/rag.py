"""RAG schemas — re-index progress events + status (brief §4).

The reindex stream emits one ``embedding`` event per entry ("converting i / N")
then a final ``done`` summary, so the UI can show the corpus being embedded. Wire
shape mirrors the triage/build NDJSON streams (CamelModel, ``by_alias``).
"""

from __future__ import annotations

from typing import Literal

from app.schemas.base import CamelModel


class RagProgressEvent(CamelModel):
    """One entry being embedded into the vector store."""

    stage: Literal["embedding"] = "embedding"
    index: int
    total: int
    name: str
    type: str


class RagDoneEvent(CamelModel):
    """Terminal summary: how many entries were (re)embedded vs. skipped (unchanged)."""

    stage: Literal["done"] = "done"
    indexed: int
    skipped: int
    total: int
    available: bool  # False when the vector store is disabled/unreachable


class RagErrorEvent(CamelModel):
    stage: Literal["error"] = "error"
    message: str


class RagStatusResponse(CamelModel):
    """Operator view: is the store reachable, and how many points this world has."""

    available: bool
    indexed: int


class RagQueryRequest(CamelModel):
    """Inspect hybrid retrieval for a world (debug/visibility surface)."""

    query: str
    k: int = 8
    prefilter: bool = False


class RagResultItem(CamelModel):
    entry_id: str
    name: str
    type: str
    score: float
    body: str


class RagQueryResponse(CamelModel):
    available: bool
    results: list[RagResultItem] = []
