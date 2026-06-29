"""Indexer — embed entities/docs on save, remove on delete (brief §4.3).

Every CRUD write calls a best-effort ``sync_*`` hook here (mirroring
``graph_writer.sync_*``): the entity is turned into a lore entry, embedded, and
upserted into Qdrant. Deletes call ``remove``. All of it is graceful — when the
vector store is disabled/unreachable the hooks no-op, so CRUD never blocks.

A content hash on each point makes re-indexing idempotent: an unchanged entry is
skipped instead of re-embedded. ``iter_reindex_storyline`` drives the live
"embedding i / N" progress stream for a whole world.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from app.core import qdrant
from app.rag import entries as adapters
from app.rag import store
from app.rag.embedder import Embedder, get_embedder
from app.rag.schema import LoreEntry
from app.rag.serializer import build_bm25_text, build_embed_text

if TYPE_CHECKING:
    from qdrant_client import QdrantClient
    from sqlalchemy.orm import Session

    from app.models import Character, ContextDocument, Scenario, Setting, Storyline

logger = logging.getLogger("velora.rag")


def _content_hash(embed_text: str, bm25_text: str) -> str:
    return hashlib.sha256(f"{embed_text}\x00{bm25_text}".encode()).hexdigest()


def _payload(entry: LoreEntry, bm25_text: str, chash: str) -> dict[str, Any]:
    fm = entry.fm
    return {
        "entry_id": fm.id,
        "type": fm.type.value,
        "name": fm.name,
        "faction": fm.faction,
        "location": fm.location,
        "tags": fm.tags,
        "storyline_id": entry.storyline_id,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "body": entry.body,
        "bm25_text": bm25_text,
        "content_hash": chash,
    }


def index_entry(client: QdrantClient, embedder: Embedder, entry: LoreEntry) -> str:
    """Embed + upsert one entry. Returns ``indexed`` | ``skipped`` | ``removed``.

    ``skipped`` when the content hash is unchanged; ``removed`` when the entry opts
    out of RAG (``include_rag`` false) — its point is deleted so de-flagging a doc
    drops it from retrieval.
    """
    if not entry.include_rag:
        store.delete_entry(client, entry.entity_type, entry.entity_id)
        return "removed"
    embed_text = build_embed_text(entry.fm, entry.body)
    bm25_text = build_bm25_text(entry.fm, entry.body)
    chash = _content_hash(embed_text, bm25_text)
    if store.existing_content_hash(client, entry.entity_type, entry.entity_id) == chash:
        return "skipped"
    store.ensure_collection(client)
    dense = embedder.embed_passages([embed_text])[0]
    sparse = embedder.embed_sparse_passages([bm25_text])[0]
    store.upsert_entry(
        client,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        dense=dense,
        sparse=sparse,
        payload=_payload(entry, bm25_text, chash),
    )
    return "indexed"


# --- best-effort CRUD hooks -------------------------------------------------


def _sync(entry: LoreEntry) -> None:
    client = qdrant.get_client()
    if client is None:
        return
    try:
        index_entry(client, get_embedder(), entry)
    except Exception as exc:  # pragma: no cover - defensive; indexing never blocks CRUD
        logger.debug("RAG index of %s:%s failed: %s", entry.entity_type, entry.entity_id, exc)


def sync_storyline(sl: Storyline) -> None:
    _sync(adapters.entry_from_storyline(sl))


def sync_character(ch: Character) -> None:
    _sync(adapters.entry_from_character(ch))


def sync_setting(st: Setting) -> None:
    _sync(adapters.entry_from_setting(st))


def sync_scenario(sc: Scenario) -> None:
    _sync(adapters.entry_from_scenario(sc))


def sync_context_document(doc: ContextDocument) -> None:
    _sync(adapters.entry_from_context_document(doc))


def remove(entity_type: str, entity_id: str) -> None:
    """Best-effort delete of an entity's point (delete hook)."""
    client = qdrant.get_client()
    if client is None:
        return
    try:
        store.delete_entry(client, entity_type, entity_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("RAG remove of %s:%s failed: %s", entity_type, entity_id, exc)


def remove_storyline(storyline_id: str) -> None:
    """Best-effort delete of every point in a world (storyline delete cascade)."""
    client = qdrant.get_client()
    if client is None:
        return
    try:
        flt = store.storyline_filter(storyline_id)
        if flt is not None:
            store.delete_by_filter(client, flt)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("RAG remove of storyline %s failed: %s", storyline_id, exc)


# --- bulk reindex + progress ------------------------------------------------


def collect_entries(db: Session, storyline_id: str) -> list[LoreEntry]:
    """Every RAG-eligible entry for a world: the storyline + its cast, settings,
    scenarios, and RAG-flagged context documents."""
    from app.services import crud  # local import avoids a crud ↔ indexer cycle

    out: list[LoreEntry] = [adapters.entry_from_storyline(crud.get_storyline(db, storyline_id))]
    out += [adapters.entry_from_character(c) for c in crud.list_characters(db, storyline_id)]
    out += [adapters.entry_from_setting(s) for s in crud.list_settings(db, storyline_id)]
    out += [adapters.entry_from_scenario(sc) for sc in crud.list_scenarios(db, storyline_id)]
    out += [
        adapters.entry_from_context_document(d)
        for d in crud.list_context_documents(db, storyline_id)
        if d.include_rag
    ]
    return out


def iter_reindex_storyline(db: Session, storyline_id: str) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``("embedding", {...})`` per entry then ``("done", {...})``.

    The route serializes these into the NDJSON progress stream. Best-effort: when
    the store is disabled it yields a single ``done`` with ``available=False``.
    """
    entries = collect_entries(db, storyline_id)
    total = len(entries)
    client = qdrant.get_client()
    if client is None:
        yield ("done", {"indexed": 0, "skipped": 0, "total": total, "available": False})
        return
    embedder = get_embedder()
    indexed = skipped = 0
    for i, entry in enumerate(entries, start=1):
        yield ("embedding", {"index": i, "total": total, "name": entry.fm.name, "type": entry.fm.type.value})
        try:
            result = index_entry(client, embedder, entry)
            if result == "indexed":
                indexed += 1
            else:
                skipped += 1
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("RAG reindex of %s failed: %s", entry.entity_id, exc)
            skipped += 1
    yield ("done", {"indexed": indexed, "skipped": skipped, "total": total, "available": True})


def storyline_status(db: Session, storyline_id: str) -> tuple[bool, int]:
    """(available, indexed_point_count) for a world — drives the RAG status surface."""
    client = qdrant.get_client()
    if client is None:
        return (False, 0)
    try:
        flt = store.storyline_filter(storyline_id)
        return (True, store.count(client, flt=flt))
    except Exception:
        return (False, 0)
