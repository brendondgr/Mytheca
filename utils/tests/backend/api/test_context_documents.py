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


def test_context_document_rejects_unknown_category(client, storyline_id):
    res = client.post(
        f"/api/storylines/{storyline_id}/context-docs",
        json={"name": "x.md", "category": "faction"},
    )
    assert res.status_code == 422


def test_context_document_unknown_storyline_404(client):
    res = client.get("/api/storylines/nope/context-docs")
    assert res.status_code == 404
