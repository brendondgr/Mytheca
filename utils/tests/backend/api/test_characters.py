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
    # Portrait prompts default to null until an image is generated + saved.
    assert body["portraitPositive"] is None
    assert body["portraitNegative"] is None


def test_character_portrait_prompts_roundtrip(client, storyline_id):
    """Create + PATCH persist the portrait prompts; GET reflects them."""
    created = client.post(
        f"/api/storylines/{storyline_id}/characters",
        json={
            "name": "Seraphine",
            "portrait": "/media/portraits/abc123.webp",
            "portraitPositive": "watercolor portrait, silver hair, regal",
            "portraitNegative": "blurry, extra fingers, text",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["portrait"] == "/media/portraits/abc123.webp"
    assert body["portraitPositive"] == "watercolor portrait, silver hair, regal"
    assert body["portraitNegative"] == "blurry, extra fingers, text"
    cid = body["id"]

    patched = client.patch(
        f"/api/characters/{cid}",
        json={
            "portraitPositive": "watercolor portrait, silver hair, crowned",
            "portraitNegative": "lowres, watermark",
        },
    )
    assert patched.status_code == 200
    data = patched.json()
    assert data["portraitPositive"] == "watercolor portrait, silver hair, crowned"
    assert data["portraitNegative"] == "lowres, watermark"
    # Untouched field preserved by the partial update.
    assert data["portrait"] == "/media/portraits/abc123.webp"

    fetched = client.get(f"/api/characters/{cid}").json()
    assert fetched["portraitPositive"] == "watercolor portrait, silver hair, crowned"
    assert fetched["portraitNegative"] == "lowres, watermark"


def test_character_voice_samples_roundtrip(client, storyline_id):
    """Create + PATCH persist the voice/tone samples; GET reflects them."""
    created = client.post(
        f"/api/storylines/{storyline_id}/characters",
        json={
            "name": "Fenwick",
            "voiceSamples": [
                {"situation": "greeted by a stranger", "sample": "State your business. I've no time for pleasantries."},
                {"situation": "offered a bribe", "sample": "Coin talks, but I decide what it says."},
            ],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert [s["situation"] for s in body["voiceSamples"]] == [
        "greeted by a stranger",
        "offered a bribe",
    ]
    assert body["voiceSamples"][0]["sample"].startswith("State your business")
    # Untagged pairs persist with an empty moment — they apply to any beat.
    assert [s["moment"] for s in body["voiceSamples"]] == ["", ""]
    cid = body["id"]

    patched = client.patch(
        f"/api/characters/{cid}",
        json={"voiceSamples": [{"situation": "cornered", "sample": "Back off. Now.", "moment": "tense"}]},
    )
    assert patched.status_code == 200
    assert patched.json()["voiceSamples"] == [
        {"situation": "cornered", "sample": "Back off. Now.", "moment": "tense"}
    ]

    fetched = client.get(f"/api/characters/{cid}").json()
    assert fetched["voiceSamples"][0]["sample"] == "Back off. Now."


def test_character_voice_samples_default_empty(client, storyline_id):
    """A character created without voice samples reads back an empty list, not null."""
    body = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Grimm"}
    ).json()
    assert body["voiceSamples"] == []


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


def test_looseness_round_trips(client, storyline_id):
    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Wren", "looseness": 2}
    ).json()["id"]
    assert client.get(f"/api/characters/{cid}").json()["looseness"] == 2

    client.patch(f"/api/characters/{cid}", json={"looseness": -1})
    assert client.get(f"/api/characters/{cid}").json()["looseness"] == -1

    # Neutral is a real state, and it is the default.
    client.patch(f"/api/characters/{cid}", json={"looseness": None})
    assert client.get(f"/api/characters/{cid}").json()["looseness"] is None


def test_looseness_defaults_to_neutral(client, storyline_id):
    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Plain"}
    ).json()["id"]
    assert client.get(f"/api/characters/{cid}").json()["looseness"] is None


def test_an_out_of_range_looseness_is_rejected(client, storyline_id):
    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Wren"}
    ).json()["id"]
    assert client.patch(f"/api/characters/{cid}", json={"looseness": 3}).status_code == 422
    assert client.patch(f"/api/characters/{cid}", json={"looseness": -3}).status_code == 422
