"""Context-document provenance links — doc↔entity many-to-many CRUD + cleanup.

The link layer records which documents were used as context for a character/setting
(build lineage + manual links). It is distinct from a doc's own ``entity_type``/
``entity_id`` OWNERSHIP scope: linking never changes storyline-level membership, and
one doc may link to several entities.
"""

from __future__ import annotations


def _make_character(client, storyline_id, name="Maerin"):
    return client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": name, "role": "Warden"}
    ).json()["id"]


def _make_doc(client, storyline_id, *, name="lore.md"):
    return client.post(
        f"/api/storylines/{storyline_id}/context-docs",
        json={"name": name, "content": "secret tunnels beneath the harbor"},
    ).json()


def test_link_create_is_idempotent_and_echoed_on_read(client, storyline_id):
    cid = _make_character(client, storyline_id)
    doc = _make_doc(client, storyline_id)

    r = client.post(
        f"/api/context-docs/{doc['id']}/links",
        json={"entityType": "character", "entityId": cid},
    )
    assert r.status_code == 200
    links = r.json()["links"]
    assert len(links) == 1
    assert links[0]["entityType"] == "character" and links[0]["entityId"] == cid

    # Re-linking the same pair does not duplicate.
    r2 = client.post(
        f"/api/context-docs/{doc['id']}/links",
        json={"entityType": "character", "entityId": cid},
    )
    assert len(r2.json()["links"]) == 1

    # The doc read (via list) also carries the link.
    listed = client.get(f"/api/storylines/{storyline_id}/context-docs").json()
    match = next(d for d in listed if d["id"] == doc["id"])
    assert match["links"][0]["entityId"] == cid


def test_list_by_linked_entity_returns_only_linked_docs(client, storyline_id):
    cid = _make_character(client, storyline_id)
    linked = _make_doc(client, storyline_id, name="built-from.md")
    _make_doc(client, storyline_id, name="unrelated.md")
    client.post(
        f"/api/context-docs/{linked['id']}/links",
        json={"entityType": "character", "entityId": cid},
    )

    docs = client.get(
        f"/api/storylines/{storyline_id}/context-docs",
        params={"linkedEntityType": "character", "linkedEntityId": cid},
    ).json()
    assert [d["name"] for d in docs] == ["built-from.md"]


def test_one_doc_links_to_multiple_entities(client, storyline_id):
    c1 = _make_character(client, storyline_id, "Maerin")
    c2 = _make_character(client, storyline_id, "Doran")
    doc = _make_doc(client, storyline_id, name="both.md")
    for cid in (c1, c2):
        client.post(
            f"/api/context-docs/{doc['id']}/links",
            json={"entityType": "character", "entityId": cid},
        )
    final = client.get(f"/api/storylines/{storyline_id}/context-docs").json()
    match = next(d for d in final if d["id"] == doc["id"])
    assert {lk["entityId"] for lk in match["links"]} == {c1, c2}


def test_unlink_removes_only_the_link(client, storyline_id):
    cid = _make_character(client, storyline_id)
    doc = _make_doc(client, storyline_id)
    client.post(
        f"/api/context-docs/{doc['id']}/links",
        json={"entityType": "character", "entityId": cid},
    )

    r = client.delete(
        f"/api/context-docs/{doc['id']}/links",
        params={"entityType": "character", "entityId": cid},
    )
    assert r.status_code == 200
    assert r.json()["links"] == []

    # The doc itself survives.
    still = client.get(f"/api/storylines/{storyline_id}/context-docs").json()
    assert any(d["id"] == doc["id"] for d in still)


def test_deleting_linked_entity_drops_link_but_keeps_doc(client, storyline_id):
    cid = _make_character(client, storyline_id)
    doc = _make_doc(client, storyline_id, name="corpus.md")
    client.post(
        f"/api/context-docs/{doc['id']}/links",
        json={"entityType": "character", "entityId": cid},
    )

    assert client.delete(f"/api/characters/{cid}").status_code == 204

    remaining = client.get(f"/api/storylines/{storyline_id}/context-docs").json()
    match = next(d for d in remaining if d["id"] == doc["id"])
    assert match["name"] == "corpus.md"  # storyline-level doc survives
    assert match["links"] == []  # dangling link cleaned up


def test_deleting_doc_cascades_its_links(client, storyline_id):
    cid = _make_character(client, storyline_id)
    doc = _make_doc(client, storyline_id)
    client.post(
        f"/api/context-docs/{doc['id']}/links",
        json={"entityType": "character", "entityId": cid},
    )
    assert client.delete(f"/api/context-docs/{doc['id']}").status_code == 204
    # The entity's linked-doc list is now empty (link went away with the doc).
    docs = client.get(
        f"/api/storylines/{storyline_id}/context-docs",
        params={"linkedEntityType": "character", "linkedEntityId": cid},
    ).json()
    assert docs == []
