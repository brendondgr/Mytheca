"""Character CRUD: scoped list/create, flat item routes, mono, cast pruning."""

from __future__ import annotations


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
