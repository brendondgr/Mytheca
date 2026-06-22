"""Storyline CRUD over the API."""

from __future__ import annotations


def test_create_list_get_update_delete(client):
    created = client.post("/api/storylines", json={"title": "Embergate", "genre": "Maritime"})
    assert created.status_code == 201
    sid = created.json()["id"]

    listed = client.get("/api/storylines")
    assert listed.status_code == 200
    assert any(s["id"] == sid for s in listed.json())

    assert client.get(f"/api/storylines/{sid}").json()["title"] == "Embergate"

    patched = client.patch(f"/api/storylines/{sid}", json={"title": "Embergate II"})
    assert patched.json()["title"] == "Embergate II"

    assert client.delete(f"/api/storylines/{sid}").status_code == 204
    assert client.get(f"/api/storylines/{sid}").status_code == 404


def test_premise_roundtrips_and_defaults_null(client):
    # Omitted on create -> null in the read model.
    bare = client.post("/api/storylines", json={"title": "Bare"})
    assert bare.status_code == 201
    assert bare.json()["premise"] is None

    # Supplied (multi-paragraph) on create -> echoed back verbatim.
    premise = "A drowned coast.\n\nThree powers circle the failing port."
    created = client.post(
        "/api/storylines", json={"title": "Embergate", "premise": premise}
    )
    assert created.status_code == 201
    sid = created.json()["id"]
    assert created.json()["premise"] == premise
    assert client.get(f"/api/storylines/{sid}").json()["premise"] == premise

    # PATCH updates the premise without touching other fields.
    patched = client.patch(
        f"/api/storylines/{sid}", json={"premise": "Rewritten world."}
    )
    assert patched.status_code == 200
    assert patched.json()["premise"] == "Rewritten world."
    assert patched.json()["title"] == "Embergate"


def test_missing_returns_error_envelope(client):
    r = client.get("/api/storylines/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_client_supplied_id_and_conflict(client):
    assert client.post("/api/storylines", json={"id": "embergate", "title": "E"}).status_code == 201
    dup = client.post("/api/storylines", json={"id": "embergate", "title": "Dup"})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "conflict"
