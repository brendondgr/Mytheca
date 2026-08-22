"""The in-play **Create image** action obeys the art style too.

The moment stream is the one image surface with no authoring form behind it, and the one
where the player may hand-write the prompt — so it is where a style could most easily be
dropped on the floor.
"""

from __future__ import annotations

import json

import httpx

from app.services import comfyui, llm, scene_moment


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _configure(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )
    client.patch("/api/options/comfy", json={"baseUrl": "http://localhost:8188"})


def _patch_llm(monkeypatch, systems: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        systems.append(system)
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
        if "moment-prompt writer" in system:
            return _resp(
                json.dumps({"positive": "two figures at a table", "negative": "", "caption": "A table."})
            )
        return _resp('<speaker:1>\n<type:character_dialogue>\n"Coin\'s easy."')

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _stub_render(monkeypatch, seen: dict):
    def fake_generate(base, workflow, **kwargs):
        seen.update(kwargs)
        return b"webp-bytes", {}

    monkeypatch.setattr(comfyui, "generate", fake_generate)
    monkeypatch.setattr(comfyui, "check_connection", lambda *a, **k: {"system": {}})
    monkeypatch.setattr(scene_moment, "save_webp", lambda d, b: "moment.webp")


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


def _moment(client, scid, psid, **body):
    return client.post(f"/api/play/{scid}/moment/stream", json={"sessionId": psid, **body})


def test_the_style_reaches_the_prompt_writer_and_the_renderer(
    client, storyline_id, monkeypatch, tmp_path
):
    _configure(client)
    systems: list[str] = []
    _patch_llm(monkeypatch, systems)
    seen: dict = {}
    _stub_render(monkeypatch, seen)

    scid = _scene(client, storyline_id)
    psid = _play(client, scid)
    res = _moment(client, scid, psid, artStyle="anime")
    assert res.status_code == 200

    moment_system = next(s for s in systems if "moment-prompt writer" in s)
    assert "anime illustration" in moment_system
    assert "cel shaded" in seen["positive"]
    assert seen["lora_enabled"] is False


def test_a_hand_written_prompt_still_gets_the_style(client, storyline_id, monkeypatch, tmp_path):
    """No agent sees this path — the render boundary is the only place the look can land."""
    _configure(client)
    _patch_llm(monkeypatch, [])
    seen: dict = {}
    _stub_render(monkeypatch, seen)

    scid = _scene(client, storyline_id)
    psid = _play(client, scid)
    _moment(client, scid, psid, prompt="a lamplit table, rain on the window", artStyle="photoreal")

    assert "photorealistic" in seen["positive"]
    assert seen["lora_enabled"] is False


def test_the_beat_records_the_style_it_was_painted_in(client, storyline_id, monkeypatch, tmp_path):
    """So a repaint starts from this picture\'s look, not the global default."""
    _configure(client)
    _patch_llm(monkeypatch, [])
    _stub_render(monkeypatch, {})

    scid = _scene(client, storyline_id)
    psid = _play(client, scid)
    res = _moment(client, scid, psid, prompt="a lamplit table", artStyle="anime")

    frames = [json.loads(line) for line in res.text.splitlines() if line.strip()]
    image = next(f for f in frames if f.get("type") == "scene_image")
    assert image["data"]["style"] == "anime"


def test_the_moment_defaults_to_the_stored_style(client, storyline_id, monkeypatch, tmp_path):
    _configure(client)
    client.patch("/api/options/comfy", json={"artStyle": "photoreal"})
    _patch_llm(monkeypatch, [])
    seen: dict = {}
    _stub_render(monkeypatch, seen)

    scid = _scene(client, storyline_id)
    psid = _play(client, scid)
    _moment(client, scid, psid, prompt="a lamplit table")

    assert "photorealistic" in seen["positive"]
