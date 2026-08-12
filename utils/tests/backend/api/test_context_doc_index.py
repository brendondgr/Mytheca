"""GET /api/storylines/{id}/context-docs/index — the name-only listing behind the @ menu."""

from __future__ import annotations


def _doc(client, storyline_id, name, content, position=0):
    return client.post(
        f"/api/storylines/{storyline_id}/context-docs",
        json={"name": name, "content": content, "position": position},
    ).json()["id"]


def test_index_omits_document_bodies(client, storyline_id):
    _doc(client, storyline_id, "maerin.md", "A very long private backstory.")

    resp = client.get(f"/api/storylines/{storyline_id}/context-docs/index")

    assert resp.status_code == 200
    (entry,) = resp.json()
    assert entry["name"] == "maerin.md"
    assert entry["charCount"] == len("A very long private backstory.")
    assert "content" not in entry
    assert "private backstory" not in resp.text


def test_index_matches_the_full_list_order_and_membership(client, storyline_id):
    _doc(client, storyline_id, "beta.md", "b")
    _doc(client, storyline_id, "alpha.md", "a")

    index = client.get(f"/api/storylines/{storyline_id}/context-docs/index").json()
    full = client.get(f"/api/storylines/{storyline_id}/context-docs").json()

    # The index is the same rows in the same (position, name) order as the full list —
    # the @ menu and the Documents page never disagree about what exists or where.
    assert [e["id"] for e in index] == [d["id"] for d in full]
    assert [e["name"] for e in index] == [d["name"] for d in full]
    assert [e["name"] for e in index] == ["beta.md", "alpha.md"]


def test_index_is_scoped_to_the_storyline(client, storyline_id):
    _doc(client, storyline_id, "mine.md", "ours")
    other = client.post(
        "/api/storylines", json={"id": "otherworld", "title": "Otherworld", "genre": "Court"}
    ).json()["id"]
    _doc(client, other, "theirs.md", "not ours")

    names = [e["name"] for e in client.get(f"/api/storylines/{storyline_id}/context-docs/index").json()]

    assert names == ["mine.md"]


def test_index_of_an_empty_world_is_empty(client, storyline_id):
    assert client.get(f"/api/storylines/{storyline_id}/context-docs/index").json() == []
