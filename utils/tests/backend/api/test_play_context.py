"""GET …/sessions/{id}/context — what the scene knows, in the player's terms.

The Inspector answers "what did the loop do"; this answers "what does the scene know". It is
assembled from the most recent turn's **already-persisted** trace rows, which is what makes it
work on a *resumed* scene — a panel that could only be filled by a live stream would be blank
exactly when a player returning to a long session most wants to ask what it still remembers.
"""

from __future__ import annotations

import json

import httpx

from app.services import llm

_EMISSION = '<speaker:1>\n<type:character_dialogue>\n"Coin\'s easy."'


def _patch_llm(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if "You read the player's DIRECTION" in system:
            return _resp(json.dumps({"requirements": [{"actor": None, "must": "the lamp goes over"}]}))
        if "You interpret" in system:
            return _resp(json.dumps({"kind": "freeform", "directive": "go"}))
        if "SITUATION-BASED follow-up" in system or "role-playing AS a specific" in system:
            return _resp(json.dumps({"choices": []}))
        if "step-by-step loop" in system:
            return _resp(json.dumps({"action": "end"}))
        if "private inner voice" in system:
            return _resp("{}")
        if "narrator of an interactive scene" in system:
            return _resp("The lamp goes over with a crash.")
        return _resp(_EMISSION)

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _configure(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _scene(client, storyline_id):
    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}
    ).json()["id"]
    return client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "suggestionsCount": 0},
    ).json()["id"]


def _play(client, scid, body):
    with client.stream("POST", f"/api/play/{scid}/turn", json={**body, "trace": True}) as resp:
        assert resp.status_code == 200
        for _ in resp.iter_lines():
            pass
    return client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]


def test_it_reports_how_far_back_the_scene_reached(client, storyline_id, monkeypatch):
    _configure(client)
    _patch_llm(monkeypatch)
    scid = _scene(client, storyline_id)
    psid = _play(client, scid, {"text": "I sit down."})

    body = client.get(f"/api/play/{scid}/sessions/{psid}/context").json()
    assert body["windowBeats"] > 0
    assert body["windowSource"] in ("detected", "configured", "fallback", "fixed")
    assert body["droppedBeats"] >= 0


def test_it_reports_what_the_player_asked_for_and_what_landed(
    client, storyline_id, monkeypatch
):
    _configure(client)
    _patch_llm(monkeypatch)
    scid = _scene(client, storyline_id)
    psid = _play(client, scid, {"text": "", "guidance": "The lamp goes over."})

    direction = client.get(f"/api/play/{scid}/sessions/{psid}/context").json()["direction"]
    assert direction["items"] == ["the lamp goes over"]
    # The narrator's prose covered it, so it is reported as delivered rather than outstanding.
    assert direction["delivered"] == ["the lamp goes over"]
    assert direction["outstanding"] == []


def test_it_reports_the_attached_files(client, storyline_id, monkeypatch):
    _configure(client)
    _patch_llm(monkeypatch)
    scid = _scene(client, storyline_id)
    doc = client.post(
        f"/api/storylines/{storyline_id}/context-docs",
        json={"name": "harbor.md", "content": "The harbour is deep and cold."},
    ).json()["id"]
    psid = _play(client, scid, {"text": "Tell me about it.", "taggedDocIds": [doc]})

    body = client.get(f"/api/play/{scid}/sessions/{psid}/context").json()
    assert "harbor.md" in body["taggedNames"]


def test_it_reports_whether_retrieval_fired(client, storyline_id, monkeypatch):
    _configure(client)
    _patch_llm(monkeypatch)
    scid = _scene(client, storyline_id)
    psid = _play(client, scid, {"text": "I sit down."})

    retrieval = client.get(f"/api/play/{scid}/sessions/{psid}/context").json()["retrieval"]
    assert set(retrieval) == {"fired", "reason", "matched"}
    assert isinstance(retrieval["fired"], bool)
    assert retrieval["reason"]


def test_a_session_with_no_turns_answers_with_zeroes_not_a_404(
    client, storyline_id, monkeypatch
):
    """"Nothing has happened yet" is a legitimate question with an honest answer."""
    _configure(client)
    scid = _scene(client, storyline_id)
    psid = client.post(f"/api/play/{scid}/sessions", json={}).json()["id"]

    resp = client.get(f"/api/play/{scid}/sessions/{psid}/context")
    assert resp.status_code == 200
    body = resp.json()
    assert body["windowBeats"] == 0
    assert body["droppedBeats"] == 0
    assert body["taggedNames"] == []
    assert body["direction"]["items"] == []
    assert body["summary"]["text"] == ""


def test_an_unknown_session_is_a_404(client, storyline_id):
    scid = _scene(client, storyline_id)
    assert client.get(f"/api/play/{scid}/sessions/ps_nope/context").status_code == 404


def test_it_answers_from_persisted_traces_so_a_resumed_scene_works(
    client, storyline_id, monkeypatch
):
    """The whole reason it reads traces rather than a live frame: the panel must be useful on
    a scene the player came back to."""
    _configure(client)
    _patch_llm(monkeypatch)
    scid = _scene(client, storyline_id)
    psid = _play(client, scid, {"text": "I sit down."})

    # Nothing streaming, nothing in flight — a cold read, exactly like a reload.
    body = client.get(f"/api/play/{scid}/sessions/{psid}/context").json()
    assert body["windowBeats"] > 0


def test_it_describes_only_the_most_recent_turn(client, storyline_id, monkeypatch):
    """"What does the scene know NOW" is a question about the state the next beat will be
    written against — folding every turn together would answer what it has ever known."""
    _configure(client)
    _patch_llm(monkeypatch)
    scid = _scene(client, storyline_id)
    doc = client.post(
        f"/api/storylines/{storyline_id}/context-docs",
        json={"name": "harbor.md", "content": "Deep and cold."},
    ).json()["id"]
    psid = _play(client, scid, {"text": "First.", "taggedDocIds": [doc]})
    _play(client, scid, {"text": "Second, with nothing attached.", "sessionId": psid})

    body = client.get(f"/api/play/{scid}/sessions/{psid}/context").json()
    assert body["taggedNames"] == [], "the previous turn's attachment leaked into 'now'"
