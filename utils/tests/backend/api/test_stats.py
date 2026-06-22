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


def test_range_locked_on_patch(client, storyline_id):
    _define_health(client, storyline_id)
    patched = client.patch(
        f"/api/storylines/{storyline_id}/stats/health",
        json={"displayName": "Vitality", "min": 50, "max": 60},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["displayName"] == "Vitality"  # descriptive change applied
    assert body["min"] == 0 and body["max"] == 100  # range stayed locked


def test_invalid_range_rejected_on_create(client, storyline_id):
    r = _define_health(client, storyline_id, key="bad", min=10, max=5, default=7)
    assert r.status_code == 422
