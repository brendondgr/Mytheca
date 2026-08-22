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


# ---- the world build (the "New Storyline" page's build step) ----------------


def test_the_world_build_paints_its_whole_cast_in_the_chosen_style(
    client, storyline_id, db_session, monkeypatch
):
    """One choice up front, applied to every render in the run.

    The world build is the surface where a *consistent* style matters most — it paints a
    whole cast and every place in one go, and a world half painted and half photoreal is
    not a world. So this drives the real populate stages and watches what the render
    helpers are handed.
    """
    from app.schemas.character import CharacterDraftResponse
    from app.schemas.setting import SettingDraftResponse
    from app.schemas.world_populate import RosterEntry
    from app.services import world_populate

    seen: list[str | None] = []
    monkeypatch.setattr(
        world_populate,
        "_render_portrait",
        lambda db, char, style=None: (seen.append(style), ("/media/portraits/x.webp", None))[1],
    )
    monkeypatch.setattr(
        world_populate,
        "_render_scene_art",
        lambda db, setting, style=None: (seen.append(style), ("/media/scenes/x.webp", None))[1],
    )
    # The drafting agents are not what is under test; stub them so the stage reaches the
    # render step without an LLM.
    monkeypatch.setattr(
        world_populate.character_agent,
        "draft_character",
        lambda *a, **k: CharacterDraftResponse(name="Mei", role="Smuggler"),
    )
    monkeypatch.setattr(
        world_populate.setting_agent,
        "draft_setting",
        lambda *a, **k: SettingDraftResponse(name="The Harbor", type="Exploration"),
    )
    monkeypatch.setattr(world_populate, "_write_voice", lambda *a, **k: None)
    monkeypatch.setattr(world_populate, "_write_starting_stats", lambda *a, **k: None)

    entries = [RosterEntry(name="Mei", seed="a wiry smuggler")]
    list(
        world_populate._populate_characters(
            db_session, storyline_id, entries, docs_overview=None, artwork=True, art_style="anime"
        )
    )
    list(
        world_populate._populate_settings(
            db_session,
            storyline_id,
            [RosterEntry(name="The Harbor", seed="fog and brine")],
            docs_overview=None,
            artwork=True,
            art_style="anime",
        )
    )

    assert seen == ["anime", "anime"], "every render in the run must wear the chosen style"


def test_the_world_build_defaults_to_no_style_so_options_decides(
    client, storyline_id, db_session, monkeypatch
):
    from app.schemas.character import CharacterDraftResponse
    from app.schemas.world_populate import RosterEntry
    from app.services import world_populate

    seen: list[str | None] = []
    monkeypatch.setattr(
        world_populate,
        "_render_portrait",
        lambda db, char, style=None: (seen.append(style), ("/media/portraits/x.webp", None))[1],
    )
    monkeypatch.setattr(
        world_populate.character_agent,
        "draft_character",
        lambda *a, **k: CharacterDraftResponse(name="Mei", role="Smuggler"),
    )
    monkeypatch.setattr(world_populate, "_write_voice", lambda *a, **k: None)
    monkeypatch.setattr(world_populate, "_write_starting_stats", lambda *a, **k: None)

    list(
        world_populate._populate_characters(
            db_session,
            storyline_id,
            [RosterEntry(name="Mei", seed="a wiry smuggler")],
            docs_overview=None,
            artwork=True,
        )
    )
    assert seen == [None], "None so the render service resolves the operator's default"


def test_the_populate_request_carries_an_art_style():
    from app.schemas.world_populate import WorldPopulateRequest

    assert WorldPopulateRequest().art_style is None
    assert (
        WorldPopulateRequest.model_validate({"artStyle": "photoreal"}).art_style == "photoreal"
    )
