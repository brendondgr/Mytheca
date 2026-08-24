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
    # `medium` is the default because it is the closest match to what shipped before
    # this control existed — an untouched scenario must read the same as it did.
    assert body["beatLength"] == "medium"


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


def test_scenario_beat_length_roundtrip_and_reject(client, storyline_id):
    """beatLength persists via create + PATCH; an unknown tier is a 422, not a shrug.

    The `Literal` at the schema boundary is the whole point: an unknown tier must fail
    here rather than reach `character_turn_agent`, where an unrecognised value would
    silently fall back to medium and the scene would quietly ignore the setting.
    """
    cid, sid = _make_refs(client, storyline_id)
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Scene", "castIds": [cid], "settingId": sid, "beatLength": "short"},
    ).json()["id"]
    assert client.get(f"/api/scenarios/{scid}").json()["beatLength"] == "short"

    for tier in ("medium", "long", "short"):
        patched = client.patch(f"/api/scenarios/{scid}", json={"beatLength": tier})
        assert patched.status_code == 200
        assert patched.json()["beatLength"] == tier

    for bad in ("tiny", "SHORT", "", "extra-long", 2):
        assert (
            client.patch(f"/api/scenarios/{scid}", json={"beatLength": bad}).status_code == 422
        ), bad
    # ...and the rejected patches left the stored value alone.
    assert client.get(f"/api/scenarios/{scid}").json()["beatLength"] == "short"


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


def test_direction_verbs_round_trip(client, storyline_id):
    """The scene's own one-tap direction verbs, appended to the built-in bar's groups."""
    verbs = [
        {"label": "Ring the bell", "group": "event", "text": "The harbour bell starts ringing."},
        {"label": "Tide turns", "group": "pace", "text": "The tide turns and everyone feels it."},
    ]
    created = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Salt", "directionVerbs": verbs},
    ).json()
    assert created["directionVerbs"] == verbs

    fetched = client.get(f"/api/storylines/{storyline_id}/scenarios").json()
    row = next(s for s in fetched if s["id"] == created["id"])
    assert row["directionVerbs"] == verbs

    updated = client.patch(
        f"/api/scenarios/{created['id']}", json={"directionVerbs": []}
    ).json()
    assert updated["directionVerbs"] == []


def test_a_scenario_written_before_verbs_existed_reads_as_none(client, storyline_id):
    """The column is nullable, so an older row must read as an empty list rather than 422."""
    created = client.post(
        f"/api/storylines/{storyline_id}/scenarios", json={"title": "Plain"}
    ).json()
    assert created["directionVerbs"] == []


def test_an_unknown_verb_group_is_refused(client, storyline_id):
    """A `Literal`, not a plain string — an unknown group would otherwise be a verb that
    silently never renders, since the bar draws by group."""
    resp = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={
            "title": "Bad",
            "directionVerbs": [{"label": "x", "group": "vibes", "text": "y"}],
        },
    )
    assert resp.status_code == 422


def test_too_many_verbs_are_refused(client, storyline_id):
    """The bar is a glance-and-tap surface; past a handful it becomes the wall of buttons
    the grouping exists to avoid."""
    resp = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={
            "title": "Too many",
            "directionVerbs": [
                {"label": f"V{i}", "group": "event", "text": "x"} for i in range(9)
            ],
        },
    )
    assert resp.status_code == 422


def test_a_verb_needs_both_a_chip_and_a_phrasing(client, storyline_id):
    """A verb hands the player a sentence to argue with — a blank one is a dead chip."""
    for bad in ({"label": "", "group": "event", "text": "y"},
                {"label": "x", "group": "event", "text": ""}):
        resp = client.post(
            f"/api/storylines/{storyline_id}/scenarios",
            json={"title": "Bad", "directionVerbs": [bad]},
        )
        assert resp.status_code == 422


def test_context_policy_round_trips_and_defaults_to_auto(client, storyline_id):
    """`auto` is the default and `NULL` reads as auto — the window fits itself unless a
    scene explicitly opts out."""
    created = client.post(
        f"/api/storylines/{storyline_id}/scenarios", json={"title": "Auto"}
    ).json()
    assert created["contextPolicy"] is None

    fixed = client.patch(
        f"/api/scenarios/{created['id']}", json={"contextPolicy": "fixed"}
    ).json()
    assert fixed["contextPolicy"] == "fixed"
    assert client.patch(
        f"/api/scenarios/{created['id']}", json={"contextPolicy": "auto"}
    ).json()["contextPolicy"] == "auto"


def test_an_unknown_context_policy_is_refused(client, storyline_id):
    resp = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Bad", "contextPolicy": "whatever"},
    )
    assert resp.status_code == 422


def test_context_beats_still_validates_even_though_it_is_fixed_mode_only(
    client, storyline_id
):
    """It is no longer a player control, but it is still a real setting under the fixed
    policy — an out-of-range value must not reach the assembler."""
    for bad in (4, 101):
        resp = client.post(
            f"/api/storylines/{storyline_id}/scenarios",
            json={"title": "Bad", "contextBeats": bad},
        )
        assert resp.status_code == 422


def test_scene_preset_round_trips(client, storyline_id):
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios", json={"title": "Preset"}
    ).json()["id"]
    assert client.get(f"/api/scenarios/{scid}").json()["scenePreset"] is None

    client.patch(f"/api/scenarios/{scid}", json={"scenePreset": "slow_burn"})
    assert client.get(f"/api/scenarios/{scid}").json()["scenePreset"] == "slow_burn"

    # Custom clears it without touching any value.
    before = client.get(f"/api/scenarios/{scid}").json()
    client.patch(f"/api/scenarios/{scid}", json={"scenePreset": None})
    after = client.get(f"/api/scenarios/{scid}").json()
    assert after["scenePreset"] is None
    assert (after["maxTurns"], after["suggestionsCount"], after["beatLength"]) == (
        before["maxTurns"],
        before["suggestionsCount"],
        before["beatLength"],
    )


def test_a_scene_preset_still_round_trips_while_the_catalogue_is_empty(client, storyline_id):
    """The strict enum is gone with the catalogue, and that is the point.

    `ScenePresetId` is built from the catalogue, and `Literal[()]` is not a type — pydantic
    raises on it at import. With no presets left it degrades to `str`, which is what stops
    every scenario written while presets existed from 500-ing on read. Restoring a preset
    restores the strict enum with no schema edit.
    """
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios", json={"title": "Preset"}
    ).json()["id"]
    resp = client.patch(f"/api/scenarios/{scid}", json={"scenePreset": "slow_burn"})
    assert resp.status_code == 200
    assert resp.json()["scenePreset"] == "slow_burn"


def test_the_controls_stay_authoritative_after_a_preset_is_named(client, storyline_id):
    """`scenePreset` records intent, not truth — moving a control leaves it set, which is
    exactly what lets the UI say "modified" and offer a reset."""
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios", json={"title": "Preset"}
    ).json()["id"]
    client.patch(
        f"/api/scenarios/{scid}",
        json={"scenePreset": "interrogation", "maxTurns": 2, "beatLength": "medium"},
    )
    client.patch(f"/api/scenarios/{scid}", json={"maxTurns": 7})

    row = client.get(f"/api/scenarios/{scid}").json()
    assert row["maxTurns"] == 7
    assert row["scenePreset"] == "interrogation"


def test_scene_preset_and_planner_mode_survive_creation(client, storyline_id):
    """`create_scenario` lists its columns explicitly, so a new one is silently dropped
    until it is added there. Both of these were, which is what this pins."""
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Made with both", "scenePreset": "fast_banter", "plannerMode": "off"},
    ).json()["id"]

    row = client.get(f"/api/scenarios/{scid}").json()
    assert row["scenePreset"] == "fast_banter"
    assert row["plannerMode"] == "off"
