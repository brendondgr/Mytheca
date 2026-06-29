"""RAG routes — reindex progress stream + status (brief §4)."""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def mem_store(monkeypatch):
    """Patch the runtime Qdrant client to an in-process :memory: instance."""
    from qdrant_client import QdrantClient

    from app.rag import store

    c = QdrantClient(":memory:")
    store.ensure_collection(c)
    monkeypatch.setattr("app.core.qdrant.get_client", lambda: c)
    return c


def _events(resp):
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def test_status_unknown_storyline_404(client):
    assert client.get("/api/storylines/nope/rag/status").status_code == 404


def test_status_reports_disabled_when_no_store(client, storyline_id):
    r = client.get(f"/api/storylines/{storyline_id}/rag/status")
    assert r.status_code == 200
    assert r.json() == {"available": False, "indexed": 0}


def test_reindex_stream_disabled_yields_single_done(client, storyline_id):
    r = client.post(f"/api/storylines/{storyline_id}/rag/reindex/stream")
    assert r.status_code == 200
    events = _events(r)
    assert len(events) == 1
    assert events[0]["stage"] == "done" and events[0]["available"] is False


def test_reindex_stream_embeds_and_status_reflects_it(client, storyline_id, mem_store):
    # The storyline exists (its create-hook ran while the store was disabled), plus
    # a character so the corpus has more than one entry.
    client.post(
        f"/api/storylines/{storyline_id}/characters",
        json={"name": "Maerin", "role": "Warden"},
    )
    r = client.post(f"/api/storylines/{storyline_id}/rag/reindex/stream")
    assert r.status_code == 200
    events = _events(r)
    assert any(e["stage"] == "embedding" for e in events)
    done = [e for e in events if e["stage"] == "done"][-1]
    # ≥2 entries (storyline + character); each is either freshly embedded or skipped
    # (the character was already embedded by its create-hook → idempotent skip).
    assert done["available"] is True and done["total"] >= 2
    assert done["indexed"] + done["skipped"] == done["total"]

    status = client.get(f"/api/storylines/{storyline_id}/rag/status").json()
    assert status["available"] is True and status["indexed"] >= 2  # both points present


def test_rag_query_disabled_returns_unavailable(client, storyline_id):
    r = client.post(f"/api/storylines/{storyline_id}/rag/query", json={"query": "anything"})
    assert r.status_code == 200
    assert r.json() == {"available": False, "results": []}


def test_rag_query_returns_ranked_results(client, storyline_id, mem_store):
    client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Maerin", "role": "Warden"})
    r = client.post(f"/api/storylines/{storyline_id}/rag/query", json={"query": "Maerin the warden"})
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert any(item["name"] == "Maerin" for item in body["results"])


def test_crud_create_indexes_into_store_via_hook(client, storyline_id, mem_store):
    """A character created while the store is reachable is embedded by the CRUD hook."""
    from app.rag import store

    before = store.count(mem_store)
    client.post(
        f"/api/storylines/{storyline_id}/characters",
        json={"name": "Brightmane", "role": "Ranger"},
    )
    assert store.count(mem_store) == before + 1


def test_deleting_a_context_doc_prunes_its_embedding(client, storyline_id, mem_store):
    from app.rag import store

    doc = client.post(
        f"/api/storylines/{storyline_id}/context-docs",
        json={"name": "a.md", "content": "secret tunnels beneath the harbor"},
    ).json()
    indexed = store.count(mem_store)
    assert indexed >= 1  # embedded by the create hook

    assert client.delete(f"/api/context-docs/{doc['id']}").status_code == 204
    assert store.count(mem_store) == indexed - 1  # embedding pruned on delete


def test_deleting_a_character_prunes_its_embedding(client, storyline_id, mem_store):
    from app.rag import store

    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Maerin", "role": "Warden"}
    ).json()["id"]
    indexed = store.count(mem_store)
    assert indexed >= 1

    assert client.delete(f"/api/characters/{cid}").status_code == 204
    assert store.count(mem_store) == indexed - 1
