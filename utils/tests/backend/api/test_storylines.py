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


def test_symbol_and_color_default_roundtrip_and_patch(client):
    # Omitted on create -> the gold-diamond defaults come back (camelCase wire).
    bare = client.post("/api/storylines", json={"title": "Bare"})
    assert bare.status_code == 201
    assert bare.json()["symbol"] == "◆"
    assert bare.json()["symbolColor"] == "#C8862A"

    # Supplied on create -> echoed back; survives a re-read.
    created = client.post(
        "/api/storylines",
        json={"title": "Sealed", "symbol": "★", "symbolColor": "#2F7D6B"},
    )
    assert created.status_code == 201
    sid = created.json()["id"]
    assert created.json()["symbol"] == "★"
    assert created.json()["symbolColor"] == "#2F7D6B"
    fetched = client.get(f"/api/storylines/{sid}").json()
    assert fetched["symbol"] == "★"
    assert fetched["symbolColor"] == "#2F7D6B"

    # PATCH updates the seal without touching other fields.
    patched = client.patch(
        f"/api/storylines/{sid}", json={"symbol": "●", "symbolColor": "#6B4A8A"}
    )
    assert patched.status_code == 200
    assert patched.json()["symbol"] == "●"
    assert patched.json()["symbolColor"] == "#6B4A8A"
    assert patched.json()["title"] == "Sealed"


def test_missing_returns_error_envelope(client):
    r = client.get("/api/storylines/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_client_supplied_id_and_conflict(client):
    assert client.post("/api/storylines", json={"id": "embergate", "title": "E"}).status_code == 201
    dup = client.post("/api/storylines", json={"id": "embergate", "title": "Dup"})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "conflict"
