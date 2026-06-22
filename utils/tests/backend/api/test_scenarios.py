"""Scenario CRUD: referential validation, camelCase, branches round-trip."""

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
