"""POST /api/play/{scenarioId}/presence — manual scene-presence override + undo path.

The cast-rail control (and its undo) posts a status change directly; it persists a
``character_status_change`` (auto=False) that folds into presence like an engine-driven one.
"""

from __future__ import annotations

import json

import httpx

from app.services import llm, presence


def _patch_llm(monkeypatch, content: str = '<speaker:1>\n<type:character_dialogue>\n"Hm."'):
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _scene(client, storyline_id):
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "suggestionsCount": 0},
    ).json()["id"]
    return cid, scid


def _play(client, scid, cid):
    resp = client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid})
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()][0]["sessionId"]


def test_set_presence_persists_returns_and_folds(client, storyline_id, monkeypatch, db_session):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scene(client, storyline_id)
    session_id = _play(client, scid, cid)

    resp = client.post(
        f"/api/play/{scid}/presence",
        json={"sessionId": session_id, "characterId": cid, "status": "left", "reason": "stepped out"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "character_status_change"
    assert body["data"]["status"] == "left" and body["data"]["auto"] is False
    assert body["data"]["characterId"] == cid

    # Folds into presence + shows up in the persisted session history.
    assert presence.current_presence(db_session, session_id).get(cid) == "left"
    history = client.get(f"/api/play/{scid}/sessions/{session_id}").json()
    assert any(e["type"] == "character_status_change" for e in history["events"])


def test_manual_override_can_resurrect_from_dead(client, storyline_id, monkeypatch, db_session):
    # The player has final say: a manual change is NOT bound by can_transition, so it may
    # bring a dead character back to present (unlike the engine's auto path).
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scene(client, storyline_id)
    session_id = _play(client, scid, cid)

    client.post(f"/api/play/{scid}/presence", json={"sessionId": session_id, "characterId": cid, "status": "dead"})
    assert presence.current_presence(db_session, session_id).get(cid) == "dead"
    r = client.post(f"/api/play/{scid}/presence", json={"sessionId": session_id, "characterId": cid, "status": "present"})
    assert r.status_code == 200
    assert presence.current_presence(db_session, session_id).get(cid) == "present"


def test_character_not_in_scene_404(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scene(client, storyline_id)
    session_id = _play(client, scid, cid)
    r = client.post(
        f"/api/play/{scid}/presence",
        json={"sessionId": session_id, "characterId": "c_ghost", "status": "left"},
    )
    assert r.status_code == 404


def test_unknown_session_404(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scene(client, storyline_id)
    r = client.post(
        f"/api/play/{scid}/presence",
        json={"sessionId": "ps_nope", "characterId": cid, "status": "left"},
    )
    assert r.status_code == 404


def test_invalid_status_rejected(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scene(client, storyline_id)
    session_id = _play(client, scid, cid)
    r = client.post(
        f"/api/play/{scid}/presence",
        json={"sessionId": session_id, "characterId": cid, "status": "vaporized"},
    )
    assert r.status_code == 422  # PresenceStatus literal rejects it at the schema boundary


def test_a_storyline_character_outside_the_cast_can_be_admitted(
    client, storyline_id, monkeypatch
):
    """A scene can gain a guest mid-play — the rail's "Elsewhere in the world", or an
    accepted `cast_request`. The guard used to be "is in this scenario's cast", which made
    the whole idea impossible."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scene(client, storyline_id)
    guest = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Kael"}
    ).json()["id"]
    session_id = _play(client, scid, cid)

    resp = client.post(
        f"/api/play/{scid}/presence",
        json={"sessionId": session_id, "characterId": guest, "status": "present"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["characterId"] == guest
    # A manual change, so the client shows no undo toast.
    assert resp.json()["data"]["auto"] is False


def test_a_character_from_another_world_is_still_refused(client, storyline_id, monkeypatch):
    """Presence must not be a way to smuggle someone in from a different storyline."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scene(client, storyline_id)
    session_id = _play(client, scid, cid)

    other = client.post("/api/storylines", json={"title": "Another World"}).json()["id"]
    foreign = client.post(
        f"/api/storylines/{other}/characters", json={"name": "Outsider"}
    ).json()["id"]

    resp = client.post(
        f"/api/play/{scid}/presence",
        json={"sessionId": session_id, "characterId": foreign, "status": "present"},
    )
    assert resp.status_code == 404
