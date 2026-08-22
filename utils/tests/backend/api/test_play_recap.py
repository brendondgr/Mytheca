"""POST …/sessions/{id}/recap — "tell me what happened", on demand.

The important property is not the prose: it is that this runs the **same agent** compaction
uses. Two summarisation paths with two prompts would drift apart in tone and, worse, in what
each considers a fact worth keeping — so the recap a player reads would disagree with the
memory the cast reads. That is why `recap_agent.summarize_history` was built as a standalone
function in the first place.
"""

from __future__ import annotations

import json

import httpx

from app.agents import recap_agent
from app.services import llm


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _configure(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _patch_llm(monkeypatch, content: str = "It all happened."):
    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if "You interpret" in system:
            return _resp(json.dumps({"kind": "freeform", "directive": "go"}))
        if "SITUATION-BASED follow-up" in system or "role-playing AS a specific" in system:
            return _resp(json.dumps({"choices": []}))
        if "step-by-step loop" in system:
            return _resp(json.dumps({"action": "end"}))
        if "private inner voice" in system:
            return _resp("{}")
        if "narrator of an interactive scene" in system:
            return _resp("The lamp gutters and the room goes quiet.")
        if "keep the memory of an ongoing scene" in system:
            return _resp(content)
        return _resp('<speaker:1>\n<type:character_dialogue>\n"Coin\'s easy."')

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _scene(client, storyline_id):
    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}
    ).json()["id"]
    return client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "suggestionsCount": 0},
    ).json()["id"]


def _play(client, scid, text="I sit down.", session_id=None):
    body = {"text": text}
    if session_id:
        body["sessionId"] = session_id
    with client.stream("POST", f"/api/play/{scid}/turn", json=body) as resp:
        assert resp.status_code == 200
        for _ in resp.iter_lines():
            pass
    return client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]


def test_it_returns_prose_about_the_scene(client, storyline_id, monkeypatch):
    _configure(client)
    _patch_llm(monkeypatch, "Mei sat down and the lamp guttered.")
    scid = _scene(client, storyline_id)
    psid = _play(client, scid)

    body = client.post(f"/api/play/{scid}/sessions/{psid}/recap", json={}).json()
    assert body["text"] == "Mei sat down and the lamp guttered."


def test_it_uses_the_same_agent_as_compaction(client, storyline_id, monkeypatch):
    """Not "a" summariser — *the* summariser. Asserted by intercepting the shared function,
    because a second path would be invisible to any output-based check until the two had
    already drifted."""
    _configure(client)
    _patch_llm(monkeypatch)
    scid = _scene(client, storyline_id)
    psid = _play(client, scid)

    seen: dict = {}

    def spy(conn, **kw):
        seen.update(kw)
        return "From the shared agent."

    monkeypatch.setattr(recap_agent, "summarize_history", spy)
    body = client.post(f"/api/play/{scid}/sessions/{psid}/recap", json={}).json()
    assert body["text"] == "From the shared agent."
    assert seen["beats"], "the shared agent was called with the scene's beats"


def test_it_honours_a_through_seq(client, storyline_id, monkeypatch):
    """The memory panel asks for "everything above the line where verbatim memory stops"."""
    _configure(client)
    _patch_llm(monkeypatch)
    scid = _scene(client, storyline_id)
    psid = _play(client, scid)
    _play(client, scid, "A second thing.", session_id=psid)

    seen: dict = {}
    monkeypatch.setattr(
        recap_agent, "summarize_history", lambda conn, **kw: (seen.update(kw), "ok")[1]
    )
    client.post(f"/api/play/{scid}/sessions/{psid}/recap", json={"throughSeq": 1})
    narrow = len(seen["beats"])

    client.post(f"/api/play/{scid}/sessions/{psid}/recap", json={})
    assert len(seen["beats"]) > narrow


def test_an_empty_session_recaps_to_nothing_rather_than_erroring(
    client, storyline_id, monkeypatch
):
    _configure(client)
    _patch_llm(monkeypatch)
    scid = _scene(client, storyline_id)
    psid = client.post(f"/api/play/{scid}/sessions", json={}).json()["id"]

    resp = client.post(f"/api/play/{scid}/sessions/{psid}/recap", json={})
    assert resp.status_code == 200
    assert resp.json()["text"] == ""


def test_an_unreachable_model_returns_an_empty_recap_not_a_500(
    client, storyline_id, monkeypatch
):
    """A recap is a convenience. It must not be able to fail a page."""
    _configure(client)
    _patch_llm(monkeypatch)
    scid = _scene(client, storyline_id)
    psid = _play(client, scid)

    monkeypatch.setattr(recap_agent, "summarize_history", lambda conn, **kw: None)
    resp = client.post(f"/api/play/{scid}/sessions/{psid}/recap", json={})
    assert resp.status_code == 200
    assert resp.json()["text"] == ""


def test_no_configured_model_is_also_an_empty_recap(client, storyline_id, monkeypatch):
    _configure(client)
    _patch_llm(monkeypatch)
    scid = _scene(client, storyline_id)
    psid = _play(client, scid)
    client.patch("/api/options/llm", json={"baseUrl": "", "model": ""})

    resp = client.post(f"/api/play/{scid}/sessions/{psid}/recap", json={})
    assert resp.status_code == 200
    assert resp.json()["text"] == ""


def test_an_unknown_session_is_a_404(client, storyline_id):
    scid = _scene(client, storyline_id)
    assert (
        client.post(f"/api/play/{scid}/sessions/ps_nope/recap", json={}).status_code == 404
    )
