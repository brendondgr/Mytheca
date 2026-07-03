"""Scenario CRUD: referential validation, camelCase, branches round-trip, scene art."""

from __future__ import annotations


def _make_refs(client, storyline_id):
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Maerin"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Tavern"}).json()["id"]
    return cid, sid


def test_create_rejects_unknown_refs(client, storyline_id):
    _, sid = _make_refs(client, storyline_id)
    r = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "X", "castIds": ["ghost"], "settingId": sid},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_reference"


def test_scenario_crud_and_camel(client, storyline_id):
    cid, sid = _make_refs(client, storyline_id)
    created = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={
            "title": "The Embergate Conspiracy",
            "castIds": [cid],
            "settingId": sid,
            "branches": [{"label": "Confront", "check": "Insight", "outcome": "x", "tag": "check_request"}],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["castIds"] == [cid] and body["settingId"] == sid
    assert body["branches"][0]["tag"] == "check_request"
    scid = body["id"]

    listed = client.get(f"/api/storylines/{storyline_id}/scenarios")
    assert [s["id"] for s in listed.json()] == [scid]

    # PATCH with a bad setting reference is rejected.
    assert client.patch(f"/api/scenarios/{scid}", json={"settingId": "ghost"}).status_code == 422

    assert client.delete(f"/api/scenarios/{scid}").status_code == 204
    assert client.get(f"/api/scenarios/{scid}").status_code == 404


def test_scenario_scene_controls_defaults(client, storyline_id):
    """New scenario defaults to max_turns=5, suggestions_count=4, context_beats=14."""
    cid, sid = _make_refs(client, storyline_id)
    body = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Scene", "castIds": [cid], "settingId": sid},
    ).json()
    assert body["maxTurns"] == 5
    assert body["suggestionsCount"] == 4
    assert body["contextBeats"] == 14


def test_scenario_scene_controls_roundtrip_and_clamp(client, storyline_id):
    """maxTurns/suggestionsCount/contextBeats persist via create + PATCH; out-of-range rejected."""
    cid, sid = _make_refs(client, storyline_id)
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={
            "title": "Scene", "castIds": [cid], "settingId": sid,
            "maxTurns": 3, "suggestionsCount": 0, "contextBeats": 30,
        },
    ).json()["id"]

    fetched = client.get(f"/api/scenarios/{scid}").json()
    assert fetched["maxTurns"] == 3 and fetched["suggestionsCount"] == 0
    assert fetched["contextBeats"] == 30

    patched = client.patch(
        f"/api/scenarios/{scid}", json={"maxTurns": 8, "suggestionsCount": 2, "contextBeats": 100}
    ).json()
    assert patched["maxTurns"] == 8 and patched["suggestionsCount"] == 2
    assert patched["contextBeats"] == 100

    # Out-of-range values are rejected by the schema.
    assert client.patch(f"/api/scenarios/{scid}", json={"suggestionsCount": 5}).status_code == 422
    assert client.patch(f"/api/scenarios/{scid}", json={"maxTurns": 0}).status_code == 422
    assert client.patch(f"/api/scenarios/{scid}", json={"contextBeats": 4}).status_code == 422
    assert client.patch(f"/api/scenarios/{scid}", json={"contextBeats": 101}).status_code == 422


def test_scenario_image_default_null(client, storyline_id):
    """Newly created scenario has null image/prompt fields."""
    cid, sid = _make_refs(client, storyline_id)
    body = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Scene", "castIds": [cid], "settingId": sid},
    ).json()
    assert body["image"] is None
    assert body["sceneArtPositive"] is None
    assert body["sceneArtNegative"] is None


def test_scenario_image_roundtrip(client, storyline_id):
    """PATCH persists image + prompts; GET reflects them."""
    cid, sid = _make_refs(client, storyline_id)
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Scene", "castIds": [cid], "settingId": sid},
    ).json()["id"]

    patch = client.patch(
        f"/api/scenarios/{scid}",
        json={
            "image": "/media/scenes/abc123.webp",
            "sceneArtPositive": "foggy harbor, watercolor",
            "sceneArtNegative": "people, text",
        },
    )
    assert patch.status_code == 200
    data = patch.json()
    assert data["image"] == "/media/scenes/abc123.webp"
    assert data["sceneArtPositive"] == "foggy harbor, watercolor"
    assert data["sceneArtNegative"] == "people, text"

    fetched = client.get(f"/api/scenarios/{scid}").json()
    assert fetched["image"] == "/media/scenes/abc123.webp"
