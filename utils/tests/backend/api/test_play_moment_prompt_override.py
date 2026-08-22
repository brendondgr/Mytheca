"""The player can write the image prompt themselves.

The prompt was already persisted on the event and already shown in the enlarged view; making
it editable turns "here is why the picture looks like that" into "here is how to get the
picture you wanted".

The property that must survive is the one `EXP-2026-08-002` is about: an image prompt describes
people by **appearance**, never by name. A hand-written prompt is exactly the hole through
which that guarantee would quietly leak back, so it is stripped like any other.
"""

from __future__ import annotations

import json

import httpx

from app.agents import moment_agent
from app.services import comfyui, llm, scene_moment


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _configure(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )
    client.patch("/api/options/comfy", json={"baseUrl": "http://localhost:8188"})


def _patch_llm(monkeypatch):
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
            return _resp("The lamp gutters.")
        return _resp('<speaker:1>\n<type:character_dialogue>\n"Coin\'s easy."')

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _stub_render(monkeypatch, tmp_path, seen: dict):
    """Capture what actually reaches ComfyUI — the only place the final prompt is observable."""

    def fake_generate(base, workflow, **kwargs):
        seen.update(kwargs)
        return b"webp-bytes", {}

    monkeypatch.setattr(comfyui, "generate", fake_generate)
    monkeypatch.setattr(scene_moment, "save_webp", lambda d, b: "moment.webp")
    monkeypatch.setattr(comfyui, "check_connection", lambda *a, **k: {"system": {}})


def _scene(client, storyline_id):
    cid = client.post(
        f"/api/storylines/{storyline_id}/characters",
        json={"name": "Mei", "appearance": "a wiry smuggler in a salt-stained coat"},
    ).json()["id"]
    return client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "suggestionsCount": 0},
    ).json()["id"]


def _play(client, scid):
    with client.stream("POST", f"/api/play/{scid}/turn", json={"text": "I sit down."}) as r:
        for _ in r.iter_lines():
            pass
    return client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]


def test_an_explicit_prompt_skips_the_agent(client, storyline_id, monkeypatch, tmp_path):
    """The player has already said what they want painted; re-deriving it would cost a call
    and override them."""
    _configure(client)
    _patch_llm(monkeypatch)
    called = {"n": 0}
    real = moment_agent.write_moment_prompt

    def spy(*a, **k):
        called["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(moment_agent, "write_moment_prompt", spy)
    seen: dict = {}
    _stub_render(monkeypatch, tmp_path, seen)

    scid = _scene(client, storyline_id)
    psid = _play(client, scid)
    resp = client.post(
        f"/api/play/{scid}/moment/stream",
        json={"sessionId": psid, "prompt": "a lamplit table, rain on the window"},
    )
    assert resp.status_code == 200
    assert called["n"] == 0, "the agent was called despite an explicit prompt"


def test_a_hand_written_prompt_still_has_names_stripped(
    client, storyline_id, monkeypatch, tmp_path
):
    """The guarantee `EXP-2026-08-002` is about: appearance, never names. A hand-written
    prompt is exactly the hole it would leak back through."""
    _configure(client)
    _patch_llm(monkeypatch)
    seen: dict = {}
    _stub_render(monkeypatch, tmp_path, seen)

    scid = _scene(client, storyline_id)
    psid = _play(client, scid)
    client.post(
        f"/api/play/{scid}/moment/stream",
        json={"sessionId": psid, "prompt": "Mei stands at the window"},
    )

    positive = str(seen.get("positive", ""))
    assert positive, "the render was never reached"
    assert "Mei" not in positive
    assert "smuggler" in positive or "coat" in positive


def test_an_empty_override_falls_back_to_the_agent(
    client, storyline_id, monkeypatch, tmp_path
):
    _configure(client)
    _patch_llm(monkeypatch)
    called = {"n": 0}
    real = moment_agent.write_moment_prompt

    def spy(*a, **k):
        called["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(moment_agent, "write_moment_prompt", spy)
    _stub_render(monkeypatch, tmp_path, {})

    scid = _scene(client, storyline_id)
    psid = _play(client, scid)
    client.post(
        f"/api/play/{scid}/moment/stream", json={"sessionId": psid, "prompt": "   "}
    )
    assert called["n"] == 1


def test_a_negative_prompt_reaches_the_renderer(client, storyline_id, monkeypatch, tmp_path):
    _configure(client)
    _patch_llm(monkeypatch)
    seen: dict = {}
    _stub_render(monkeypatch, tmp_path, seen)

    scid = _scene(client, storyline_id)
    psid = _play(client, scid)
    client.post(
        f"/api/play/{scid}/moment/stream",
        json={"sessionId": psid, "prompt": "a lamplit table", "negative": "blurry, text"},
    )
    assert "blurry" in str(seen.get("negative", ""))
