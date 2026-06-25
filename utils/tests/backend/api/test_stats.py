"""Stat definitions + clamped character values over the API."""

from __future__ import annotations


def _define_health(client, storyline_id, **over):
    body = {"key": "health", "displayName": "Health", "min": 0, "max": 100, "default": 100}
    body.update(over)
    return client.post(f"/api/storylines/{storyline_id}/stats", json=body)


def test_define_list_and_clamp(client, storyline_id):
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Maerin"}).json()["id"]

    created = _define_health(client, storyline_id)
    assert created.status_code == 201
    assert created.json()["displayName"] == "Health" and created.json()["appliesTo"] == ["character"]

    assert [s["key"] for s in client.get(f"/api/storylines/{storyline_id}/stats").json()] == ["health"]

    # Values are clamped to [min, max] at both ends.
    assert client.put(f"/api/characters/{cid}/stats", json={"health": 250}).json() == {"health": 100}
    assert client.put(f"/api/characters/{cid}/stats", json={"health": -40}).json() == {"health": 0}
    assert client.get(f"/api/characters/{cid}/stats").json() == {"health": 0}


def test_reject_unknown_stat_key(client, storyline_id):
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "X"}).json()["id"]
    r = client.put(f"/api/characters/{cid}/stats", json={"ghost": 5})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_stat"


def test_duplicate_stat_key_conflicts(client, storyline_id):
    _define_health(client, storyline_id)
    assert _define_health(client, storyline_id, displayName="Dup").status_code == 409


def test_range_freely_editable_and_reclamps(client, storyline_id):
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "R"}).json()["id"]
    _define_health(client, storyline_id)
    client.put(f"/api/characters/{cid}/stats", json={"health": 90})

    # Range is now freely editable — narrowing it re-clamps existing values.
    patched = client.patch(
        f"/api/storylines/{storyline_id}/stats/health",
        json={"displayName": "Vitality", "min": 50, "max": 60},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["displayName"] == "Vitality" and body["min"] == 50 and body["max"] == 60
    # The character's 90 was pulled back into the new [50, 60] range.
    assert client.get(f"/api/characters/{cid}/stats").json() == {"health": 60}


def test_invalid_range_rejected_on_create(client, storyline_id):
    r = _define_health(client, storyline_id, key="bad", min=10, max=5, default=7)
    assert r.status_code == 422


def test_invalid_range_rejected_on_patch(client, storyline_id):
    _define_health(client, storyline_id)
    r = client.patch(
        f"/api/storylines/{storyline_id}/stats/health", json={"min": 80, "max": 50}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_range"


def test_bands_roundtrip_and_validate(client, storyline_id):
    bands = [
        {"min": 0, "max": 20, "label": "Nearly dead"},
        {"min": 81, "max": 100, "label": "Very healthy"},
    ]
    created = _define_health(client, storyline_id, bands=bands)
    assert created.status_code == 201
    assert created.json()["bands"] == bands

    # Bands are editable via PATCH.
    new_bands = [{"min": 0, "max": 100, "label": "Alive"}]
    patched = client.patch(
        f"/api/storylines/{storyline_id}/stats/health", json={"bands": new_bands}
    )
    assert patched.status_code == 200 and patched.json()["bands"] == new_bands

    # A band with min > max or a blank label is rejected.
    bad = _define_health(client, storyline_id, key="b2", bands=[{"min": 50, "max": 10, "label": "x"}])
    assert bad.status_code == 422
    blank = _define_health(client, storyline_id, key="b3", bands=[{"min": 0, "max": 5, "label": " "}])
    assert blank.status_code == 422


def test_delete_stat_prunes_character_values(client, storyline_id):
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "D"}).json()["id"]
    _define_health(client, storyline_id)
    client.put(f"/api/characters/{cid}/stats", json={"health": 50})
    assert client.get(f"/api/characters/{cid}/stats").json() == {"health": 50}

    assert client.delete(f"/api/storylines/{storyline_id}/stats/health").status_code == 204
    # Definition gone, and the character's value for it was pruned.
    assert [s["key"] for s in client.get(f"/api/storylines/{storyline_id}/stats").json()] == []
    assert client.get(f"/api/characters/{cid}/stats").json() == {}
    # Deleting a missing stat is a 404.
    assert client.delete(f"/api/storylines/{storyline_id}/stats/health").status_code == 404
