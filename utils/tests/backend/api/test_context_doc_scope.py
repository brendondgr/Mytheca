"""Entity-scoped context documents — scoped CRUD + delete cascade (RAG phase 6)."""

from __future__ import annotations


def _make_character(client, storyline_id, name="Maerin"):
    return client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": name, "role": "Warden"}
    ).json()["id"]


def _make_doc(client, storyline_id, *, name, entity_type=None, entity_id=None):
    body = {"name": name, "content": "secret tunnels beneath the harbor"}
    if entity_type:
        body["entityType"] = entity_type
        body["entityId"] = entity_id
    return client.post(f"/api/storylines/{storyline_id}/context-docs", json=body)


def test_entity_scoped_doc_roundtrips_and_lists_both_ways(client, storyline_id):
    cid = _make_character(client, storyline_id)
    r = _make_doc(client, storyline_id, name="maerin-notes.md", entity_type="character", entity_id=cid)
    assert r.status_code == 201
    doc = r.json()
    assert doc["entityType"] == "character" and doc["entityId"] == cid

    scoped = client.get(
        f"/api/storylines/{storyline_id}/context-docs", params={"entityType": "character", "entityId": cid}
    ).json()
    assert [d["name"] for d in scoped] == ["maerin-notes.md"]

    # The unscoped list still returns it (it's part of the world corpus).
    all_docs = client.get(f"/api/storylines/{storyline_id}/context-docs").json()
    assert any(d["name"] == "maerin-notes.md" for d in all_docs)


def test_scoped_list_excludes_other_entities(client, storyline_id):
    c1 = _make_character(client, storyline_id, "Maerin")
    c2 = _make_character(client, storyline_id, "Doran")
    _make_doc(client, storyline_id, name="a.md", entity_type="character", entity_id=c1)
    scoped_c2 = client.get(
        f"/api/storylines/{storyline_id}/context-docs", params={"entityType": "character", "entityId": c2}
    ).json()
    assert scoped_c2 == []


def test_deleting_an_entity_purges_its_scoped_docs(client, storyline_id):
    cid = _make_character(client, storyline_id)
    _make_doc(client, storyline_id, name="maerin-notes.md", entity_type="character", entity_id=cid)
    # storyline-level doc must survive the character delete
    _make_doc(client, storyline_id, name="world.md")

    assert client.delete(f"/api/characters/{cid}").status_code == 204

    remaining = client.get(f"/api/storylines/{storyline_id}/context-docs").json()
    names = {d["name"] for d in remaining}
    assert "maerin-notes.md" not in names  # entity-scoped doc purged
    assert "world.md" in names  # storyline-level doc untouched


def test_storyline_level_docs_default_to_unscoped(client, storyline_id):
    doc = _make_doc(client, storyline_id, name="lore.md").json()
    assert doc["entityType"] is None and doc["entityId"] is None
