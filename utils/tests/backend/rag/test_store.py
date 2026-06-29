"""Qdrant store — upsert / hybrid search / delete against in-process :memory: (brief §4)."""

from __future__ import annotations

import pytest

from app.rag import store
from app.rag.embedder import HashEmbedder


@pytest.fixture
def client():
    from qdrant_client import QdrantClient

    c = QdrantClient(":memory:")
    store.ensure_collection(c)
    return c


@pytest.fixture
def embedder():
    return HashEmbedder()


def _index(client, embedder, *, entity_type, entity_id, storyline_id, text, **payload):
    dense = embedder.embed_passages([text])[0]
    sparse = embedder.embed_sparse_passages([text])[0]
    body = {"entry_id": entity_id, "entity_type": entity_type, "storyline_id": storyline_id, "body": text}
    body.update(payload)
    return store.upsert_entry(
        client, entity_type=entity_type, entity_id=entity_id, dense=dense, sparse=sparse, payload=body
    )


def test_ensure_collection_is_idempotent(client):
    store.ensure_collection(client)  # second call must not raise
    assert client.collection_exists(store.get_settings().qdrant_collection)


def test_upsert_then_dense_search_returns_the_point(client, embedder):
    _index(client, embedder, entity_type="character", entity_id="c1", storyline_id="w1",
           text="a harbor warden patrols the fog", name="Maerin")
    q = embedder.embed_query("warden patrols the fog")
    hits = store.dense_search(client, q, k=5, flt=store.storyline_filter("w1"))
    assert hits and hits[0].entry_id == "c1"
    assert hits[0].payload["name"] == "Maerin"


def test_sparse_search_returns_the_point(client, embedder):
    _index(client, embedder, entity_type="character", entity_id="c1", storyline_id="w1",
           text="a harbor warden patrols the fog")
    sq = embedder.embed_sparse_query("warden fog")
    hits = store.sparse_search(client, sq, k=5, flt=store.storyline_filter("w1"))
    assert hits and hits[0].entry_id == "c1"


def test_storyline_filter_isolates_corpora(client, embedder):
    _index(client, embedder, entity_type="character", entity_id="c1", storyline_id="w1",
           text="the harbor warden")
    _index(client, embedder, entity_type="character", entity_id="c2", storyline_id="w2",
           text="the harbor warden")
    q = embedder.embed_query("harbor warden")
    hits = store.dense_search(client, q, k=10, flt=store.storyline_filter("w1"))
    assert {h.entry_id for h in hits} == {"c1"}  # w2's identical text is filtered out


def test_delete_entry_removes_the_point(client, embedder):
    _index(client, embedder, entity_type="character", entity_id="c1", storyline_id="w1", text="warden")
    assert store.count(client) == 1
    store.delete_entry(client, "character", "c1")
    assert store.count(client) == 0


def test_reupsert_is_idempotent_in_place(client, embedder):
    _index(client, embedder, entity_type="setting", entity_id="s1", storyline_id="w1", text="the wharf")
    _index(client, embedder, entity_type="setting", entity_id="s1", storyline_id="w1", text="the rebuilt wharf")
    assert store.count(client) == 1  # same point id → overwrite, not duplicate


def test_point_id_is_namespaced_by_entity_type():
    # A character and a context document that happen to share a raw id never collide.
    assert store.point_id("character", "x1") != store.point_id("context_document", "x1")
    assert store.point_id("character", "x1") == store.point_id("character", "x1")  # stable
