"""`artStyle` on the request body reaches the agent and the renderer, on every surface.

The user-facing promise is that the picker works *throughout* the site — characters,
places, scenarios, and the in-play scene image alike — so each of the five routes gets its
own case rather than trusting that one implies the others.
"""

from __future__ import annotations

import json

import httpx

from app.services import comfyui, llm, portraits, scene_art, scene_moment


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _configure(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )
    client.patch("/api/options/comfy", json={"baseUrl": "http://localhost:8188"})


def _patch_prompt_llm(monkeypatch, seen: dict):
    """Answer any prompt-writing call with a fixed pair, recording the system prompt."""

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        seen["system"] = body["messages"][0]["content"]
        return _resp(json.dumps({"positive": "a subject", "negative": "blurry"}))

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _stub_render(monkeypatch, seen: dict):
    def fake_generate(base, workflow, **kwargs):
        seen.update(kwargs)
        return b"webp-bytes", {}

    monkeypatch.setattr(comfyui, "generate", fake_generate)
    monkeypatch.setattr(comfyui, "check_connection", lambda *a, **k: {"system": {}})
    monkeypatch.setattr(portraits, "save_webp", lambda d, b: "p.webp")
    monkeypatch.setattr(scene_art, "save_webp", lambda d, b: "s.webp")
    monkeypatch.setattr(scene_moment, "save_webp", lambda d, b: "m.webp")


# ---- prompt-writing routes -------------------------------------------------


def test_portrait_prompts_are_written_for_the_requested_style(client, monkeypatch):
    _configure(client)
    seen: dict = {}
    _patch_prompt_llm(monkeypatch, seen)

    res = client.post(
        "/api/characters/portrait-prompts",
        json={"name": "Mei", "appearance": "a wiry smuggler", "artStyle": "anime"},
    )
    assert res.status_code == 200
    assert "anime portrait" in seen["system"]


def test_setting_scene_art_prompts_are_written_for_the_requested_style(client, monkeypatch):
    _configure(client)
    seen: dict = {}
    _patch_prompt_llm(monkeypatch, seen)

    res = client.post(
        "/api/settings/scene-art-prompts",
        json={"name": "The Harbor", "atmosphere": "fog and brine", "artStyle": "photoreal"},
    )
    assert res.status_code == 200
    assert "photorealistic" in seen["system"]


def test_scenario_scene_art_prompts_are_written_for_the_requested_style(client, monkeypatch):
    _configure(client)
    seen: dict = {}
    _patch_prompt_llm(monkeypatch, seen)

    res = client.post(
        "/api/scenarios/scene-art-prompts",
        json={"title": "Standoff", "tone": "tense", "artStyle": "anime"},
    )
    assert res.status_code == 200
    assert "anime background art" in seen["system"]


def test_omitting_the_style_uses_the_stored_default(client, monkeypatch):
    _configure(client)
    client.patch("/api/options/comfy", json={"artStyle": "photoreal"})
    seen: dict = {}
    _patch_prompt_llm(monkeypatch, seen)

    client.post("/api/characters/portrait-prompts", json={"name": "Mei", "appearance": "wiry"})
    assert "photorealistic portrait" in seen["system"]


# ---- render routes ---------------------------------------------------------


def test_the_portrait_render_route_passes_the_style_through(client, monkeypatch):
    _configure(client)
    seen: dict = {}
    _stub_render(monkeypatch, seen)

    res = client.post(
        "/api/characters/portrait", json={"positive": "a wiry smuggler", "artStyle": "anime"}
    )
    assert res.status_code == 200
    assert "cel shaded" in seen["positive"]
    assert seen["lora_enabled"] is False


def test_the_setting_render_route_passes_the_style_through(client, monkeypatch):
    _configure(client)
    seen: dict = {}
    _stub_render(monkeypatch, seen)

    res = client.post(
        "/api/settings/scene-art", json={"positive": "a fog-bound harbor", "artStyle": "photoreal"}
    )
    assert res.status_code == 200
    assert "photorealistic" in seen["positive"]
    assert seen["lora_enabled"] is False


def test_the_scenario_render_route_passes_the_style_through(client, monkeypatch):
    _configure(client)
    seen: dict = {}
    _stub_render(monkeypatch, seen)

    res = client.post(
        "/api/scenarios/scene-art", json={"positive": "a candlelit hall", "artStyle": "anime"}
    )
    assert res.status_code == 200
    assert "anime background art" in seen["positive"]


def test_the_render_routes_default_to_painted_with_its_lora(client, monkeypatch):
    """Unchanged behaviour for anyone who never touches the picker."""
    _configure(client)
    seen: dict = {}
    _stub_render(monkeypatch, seen)

    client.post("/api/characters/portrait", json={"positive": "a wiry smuggler"})
    assert seen["lora_name"] == "zit_watercolor.safetensors"
    assert seen["lora_enabled"] is True
