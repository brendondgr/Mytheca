"""Character CRUD: scoped list/create, flat item routes, mono, cast pruning."""

from __future__ import annotations


def test_character_create_survives_graph_down(client, db_session, storyline_id, monkeypatch):
    """CRUD must not break when the Story Graph is enabled but unreachable (§ best-effort)."""
    from app.services import graph_writer, type_registry

    type_registry.seed_builtin_types(db_session)  # so validation passes; the write then fails
    monkeypatch.setattr(graph_writer.neo4j, "is_enabled", lambda: True)

    def _boom(**kwargs):
        raise RuntimeError("graph down")

    monkeypatch.setattr(graph_writer.neo4j, "write_session", _boom)

    created = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Maerin Voss"}
    )
    assert created.status_code == 201  # the graph hiccup was swallowed; CRUD succeeded
    cid = created.json()["id"]
    assert client.delete(f"/api/characters/{cid}").status_code == 204  # delete too


def test_character_crud_and_mono(client, storyline_id):
    created = client.post(
        f"/api/storylines/{storyline_id}/characters",
        json={"name": "Maerin Voss", "role": "Antagonist"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["mono"] == "MV"  # derived by the backend
    cid = body["id"]

    listed = client.get(f"/api/storylines/{storyline_id}/characters")
    assert [c["id"] for c in listed.json()] == [cid]

    assert client.get(f"/api/characters/{cid}").json()["name"] == "Maerin Voss"

    patched = client.patch(f"/api/characters/{cid}", json={"name": "Wren Calloway"})
    assert patched.json()["mono"] == "WC"  # re-derived on name change

    assert client.delete(f"/api/characters/{cid}").status_code == 204
    assert client.get(f"/api/characters/{cid}").status_code == 404


def test_character_base_identity_fields_roundtrip(client, storyline_id):
    created = client.post(
        f"/api/storylines/{storyline_id}/characters",
        json={
            "name": "Nyssa",
            "appearance": "Veiled in salt-grey linen, eyes like still water.",
            "background": "Born to the oracle line; raised on the tideline.",
            "personality": "Serene, cryptic, certain of what others cannot see.",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["appearance"].startswith("Veiled in salt-grey")
    assert body["background"].startswith("Born to the oracle")
    assert body["personality"].startswith("Serene, cryptic")
    # Unset prose / portrait default to null, not "".
    assert body["portrait"] is None
    cid = body["id"]

    patched = client.patch(
        f"/api/characters/{cid}",
        json={"appearance": "Now stooped, her veil frayed at the hem."},
    )
    assert patched.status_code == 200
    assert patched.json()["appearance"].startswith("Now stooped")
    # Untouched fields are preserved by the partial update.
    assert patched.json()["personality"].startswith("Serene, cryptic")


def test_character_defaults_have_null_base_identity(client, storyline_id):
    body = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Grimm"}
    ).json()
    assert body["appearance"] is None
    assert body["background"] is None
    assert body["personality"] is None
    assert body["portrait"] is None


def test_list_for_unknown_storyline_is_404(client):
    assert client.get("/api/storylines/ghost/characters").status_code == 404


def test_delete_character_pruned_from_scenario_cast(client, storyline_id):
    a = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Aldous"}).json()["id"]
    b = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Wren"}).json()["id"]
    s = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Tavern"}).json()["id"]
    sc = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Plot", "castIds": [a, b], "settingId": s},
    ).json()["id"]

    client.delete(f"/api/characters/{a}")
    assert client.get(f"/api/scenarios/{sc}").json()["castIds"] == [b]
