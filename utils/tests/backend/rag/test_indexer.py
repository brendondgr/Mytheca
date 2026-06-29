"""Indexer — embed-on-save idempotency, removal, and bulk reindex (brief §4.3)."""

from __future__ import annotations

import pytest

from app.models import Character, ContextDocument, Scenario, Setting, Storyline
from app.rag import indexer, store
from app.rag.embedder import HashEmbedder
from app.rag.entries import entry_from_character, entry_from_context_document


@pytest.fixture
def mem_client(monkeypatch):
    from qdrant_client import QdrantClient

    c = QdrantClient(":memory:")
    store.ensure_collection(c)
    monkeypatch.setattr("app.core.qdrant.get_client", lambda: c)
    return c


def _char(**over):
    base = dict(id="c1", storyline_id="w1", name="Maerin", role="Warden", traits="brave", appearance="tall")
    base.update(over)
    return Character(**base)


def test_index_entry_indexes_then_skips_then_reindexes(mem_client):
    e = HashEmbedder()
    assert indexer.index_entry(mem_client, e, entry_from_character(_char())) == "indexed"
    assert indexer.index_entry(mem_client, e, entry_from_character(_char())) == "skipped"
    # a real content change re-embeds in place (same point id → no duplicate)
    assert indexer.index_entry(mem_client, e, entry_from_character(_char(background="orphaned"))) == "indexed"
    assert store.count(mem_client) == 1


def test_index_entry_removes_when_rag_disabled(mem_client):
    e = HashEmbedder()
    doc = ContextDocument(id="cd1", storyline_id="w1", name="x.md", content="hello", category="other", include_rag=True)
    indexer.index_entry(mem_client, e, entry_from_context_document(doc))
    assert store.count(mem_client) == 1
    doc.include_rag = False
    assert indexer.index_entry(mem_client, e, entry_from_context_document(doc)) == "removed"
    assert store.count(mem_client) == 0


def _seed(db):
    sl = Storyline(id="w1", title="Embergate", genre="Maritime")
    sl.characters.append(Character(id="c1", storyline_id="w1", name="Maerin", role="Warden"))
    sl.settings.append(Setting(id="s1", storyline_id="w1", name="Wharf", type="Harbor", desc="a pier"))
    sl.scenarios.append(Scenario(id="sc1", storyline_id="w1", title="Low Tide", goal="find the body"))
    sl.context_documents.append(ContextDocument(id="cd1", storyline_id="w1", name="a.md", content="lore", include_rag=True))
    sl.context_documents.append(ContextDocument(id="cd2", storyline_id="w1", name="b.md", content="skip", include_rag=False))
    db.add(sl)
    db.commit()


def test_collect_entries_gathers_world_excluding_non_rag_docs(db_session):
    _seed(db_session)
    entries = indexer.collect_entries(db_session, "w1")
    assert sorted(e.entity_type for e in entries) == [
        "character", "context_document", "scenario", "setting", "storyline"
    ]  # cd2 (include_rag False) is excluded


def test_iter_reindex_streams_embedding_events_then_done(db_session, mem_client):
    _seed(db_session)
    events = list(indexer.iter_reindex_storyline(db_session, "w1"))
    stages = [s for s, _ in events]
    assert stages.count("embedding") == 5  # storyline + char + setting + scenario + 1 rag doc
    assert stages[-1] == "done"
    done = events[-1][1]
    assert done["indexed"] == 5 and done["total"] == 5 and done["available"] is True
    assert store.count(mem_client) == 5


def test_iter_reindex_when_store_disabled_reports_unavailable(db_session):
    _seed(db_session)  # no mem_client patch → get_client() is None (QDRANT_URL unset)
    events = list(indexer.iter_reindex_storyline(db_session, "w1"))
    assert len(events) == 1
    stage, data = events[0]
    assert stage == "done" and data["available"] is False


def test_storyline_status_counts_indexed_points(db_session, mem_client):
    _seed(db_session)
    list(indexer.iter_reindex_storyline(db_session, "w1"))
    available, indexed = indexer.storyline_status(db_session, "w1")
    assert available is True and indexed == 5
