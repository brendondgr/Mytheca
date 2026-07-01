"""Context-document CRUD over the API (the persisted triaged RAG corpus)."""

from __future__ import annotations


def test_context_document_crud(client, storyline_id):
    created = client.post(
        f"/api/storylines/{storyline_id}/context-docs",
        json={
            "name": "maerin.md",
            "content": "Maerin Voss is a harbor smuggler...",
            "category": "character",
            "includeDraft": False,
            "includeRag": True,
        },
    )
    assert created.status_code == 201
    body = created.json()
    cid = body["id"]
    assert cid.startswith("cd_")
    assert body["category"] == "character"
    assert body["includeRag"] is True
    assert body["includeDraft"] is False
    # char_count is derived from the content length.
    assert body["charCount"] == len("Maerin Voss is a harbor smuggler...")

    listed = client.get(f"/api/storylines/{storyline_id}/context-docs")
    assert [d["id"] for d in listed.json()] == [cid]

    patched = client.patch(
        f"/api/context-docs/{cid}", json={"includeDraft": True, "content": "shorter"}
    )
    assert patched.status_code == 200
    assert patched.json()["includeDraft"] is True
    assert patched.json()["charCount"] == len("shorter")

    assert client.delete(f"/api/context-docs/{cid}").status_code == 204
    assert client.get(f"/api/storylines/{storyline_id}/context-docs").json() == []


def test_context_document_defaults(client, storyline_id):
    body = client.post(
        f"/api/storylines/{storyline_id}/context-docs", json={"name": "lore.txt"}
    ).json()
    # Default triage: "other" bucket, RAG on, Draft off, upload source.
    assert body["category"] == "other"
    assert body["includeRag"] is True
    assert body["includeDraft"] is False
    assert body["source"] == "upload"
    assert body["content"] == ""
    assert body["charCount"] == 0


def test_context_document_bulk_create_and_ordering(client, storyline_id):
    res = client.post(
        f"/api/storylines/{storyline_id}/context-docs/bulk",
        json={
            "docs": [
                {"name": "a.md", "category": "setting", "includeDraft": True},
                {"name": "b.md", "category": "other"},
                {"name": "c.md", "category": "character"},
            ]
        },
    )
    assert res.status_code == 201
    assert len(res.json()) == 3
    # Persisted in submission order (position-stable).
    listed = client.get(f"/api/storylines/{storyline_id}/context-docs").json()
    assert [d["name"] for d in listed] == ["a.md", "b.md", "c.md"]
    assert listed[0]["category"] == "setting"
    assert listed[0]["includeDraft"] is True


def test_context_document_bulk_create_indexes_rag_in_parallel(client, storyline_id, monkeypatch):
    # With a vector store available, the bulk commit embeds the RAG-eligible docs
    # concurrently (bounded by authoringConcurrency); each lands as a point.
    from qdrant_client import QdrantClient

    from app.rag import store

    mem = QdrantClient(":memory:")
    store.ensure_collection(mem)
    monkeypatch.setattr("app.core.qdrant.get_client", lambda: mem)
    client.patch("/api/options/llm", json={"authoringConcurrency": 4})

    res = client.post(
        f"/api/storylines/{storyline_id}/context-docs/bulk",
        json={
            "docs": [
                {"name": f"{i}.md", "category": "other", "content": f"lore {i}", "includeRag": True}
                for i in range(5)
            ]
        },
    )
    assert res.status_code == 201
    assert store.count(mem) == 5  # all embedded, serialized writes → none lost


def test_context_document_rejects_unknown_category(client, storyline_id):
    res = client.post(
        f"/api/storylines/{storyline_id}/context-docs",
        json={"name": "x.md", "category": "faction"},
    )
    assert res.status_code == 422


def test_context_document_unknown_storyline_404(client):
    res = client.get("/api/storylines/nope/context-docs")
    assert res.status_code == 404
