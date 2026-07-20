"""Mytheca Hybrid RAG package.

Entry-based markdown lore → structured front matter → prefix-fusion serialization
→ fastembed dense + BM25 sparse vectors in Qdrant → RRF-fused hybrid retrieval
injected into the authoring agents. Best-effort throughout (mirrors the Neo4j
substrate): CRUD and the test suite run with no Qdrant / no embedding model.

See ``docs/rag.md`` and the source brief
``Documents/Plans/Mytheca/1.mytheca-rag-implementation-plan.md``.
"""

from __future__ import annotations

from app.rag.entries import (
    entry_from_character,
    entry_from_context_document,
    entry_from_scenario,
    entry_from_setting,
    entry_from_storyline,
)
from app.rag.schema import EntryType, Frontmatter, LoreEntry
from app.rag.serializer import build_bm25_text, build_embed_text

__all__ = [
    "EntryType",
    "Frontmatter",
    "LoreEntry",
    "build_bm25_text",
    "build_embed_text",
    "entry_from_character",
    "entry_from_context_document",
    "entry_from_scenario",
    "entry_from_setting",
    "entry_from_storyline",
]
