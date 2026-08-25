"""Options/settings store over the API (LLM config + library defaults)."""

from __future__ import annotations


def test_get_returns_defaults(client):
    body = client.get("/api/options").json()
    assert "llm" in body and "library" in body
    assert body["llm"]["hasApiKey"] is False
    assert body["llm"]["apiKeyHint"] is None
    # Params carry sensible defaults in camelCase.
    assert body["llm"]["params"]["maxTokens"] == 512
    assert body["library"]["openLastStoryline"] is True
    # ComfyUI config ships with the bundled workflow + default params.
    assert body["comfy"]["workflow"] == "ZiT-Workflow.json"
    assert body["comfy"]["params"]["width"] == 1024
    # Authoring concurrency defaults from BUILD_MAX_CONCURRENCY (3).
    assert body["llm"]["authoringConcurrency"] == 3


def test_patch_llm_authoring_concurrency(client):
    patched = client.patch("/api/options/llm", json={"authoringConcurrency": 6}).json()
    assert patched["authoringConcurrency"] == 6
    # Persists across a fresh GET.
    assert client.get("/api/options").json()["llm"]["authoringConcurrency"] == 6
    # Clamped to a floor of 1 (a 0/negative would disable the pool).
    assert client.patch("/api/options/llm", json={"authoringConcurrency": 0}).json()[
        "authoringConcurrency"
    ] == 1


def test_patch_llm_persists_and_masks_key(client):
    patched = client.patch(
        "/api/options/llm",
        json={
            "baseUrl": "http://localhost:7070/v1/",
            "model": "llama-3.1-8b",
            "apiKey": "sk-secret-AB12",
            "params": {"temperature": 0.2, "maxTokens": 256},
        },
    )
    assert patched.status_code == 200
    data = patched.json()
    # base URL is trimmed, key is masked and never returned in clear.
    assert data["baseUrl"] == "http://localhost:7070/v1"
    assert data["model"] == "llama-3.1-8b"
    assert data["hasApiKey"] is True
    assert data["apiKeyHint"] == "…AB12"
    assert "sk-secret-AB12" not in patched.text
    assert data["params"]["temperature"] == 0.2

    # Persists across a fresh GET; key still absent from the payload.
    again = client.get("/api/options").json()["llm"]
    assert again["model"] == "llama-3.1-8b"
    assert again["hasApiKey"] is True
    assert "sk-secret-AB12" not in client.get("/api/options").text


def test_patch_llm_omitting_key_keeps_it_and_empty_clears_it(client):
    client.patch("/api/options/llm", json={"apiKey": "sk-keep-ME99"})
    # Omitting apiKey keeps the stored one.
    kept = client.patch("/api/options/llm", json={"model": "m2"}).json()
    assert kept["hasApiKey"] is True
    assert kept["apiKeyHint"] == "…ME99"
    # Empty string clears it.
    cleared = client.patch("/api/options/llm", json={"apiKey": ""}).json()
    assert cleared["hasApiKey"] is False
    assert cleared["apiKeyHint"] is None


def test_patch_library_persists(client):
    patched = client.patch(
        "/api/options/library",
        json={"defaultStorylineId": "embergate", "openLastStoryline": False},
    )
    assert patched.status_code == 200
    data = patched.json()
    assert data["defaultStorylineId"] == "embergate"
    assert data["openLastStoryline"] is False
    assert client.get("/api/options").json()["library"]["defaultStorylineId"] == "embergate"


# ---- inference-engine detection diagnostics --------------------------------


def _patch_upstream(monkeypatch, handler):
    import httpx

    from app.services import llm

    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(llm, "get_http_client", factory)


def test_llm_backend_endpoint_reports_detected_engine(client, monkeypatch):
    import httpx

    from app.services import llm_backend

    llm_backend.clear_cache()
    client.patch("/api/options/llm", json={"baseUrl": "http://localhost:8000/v1"})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            return httpx.Response(200, json={"version": "0.21.0"})
        return httpx.Response(404)

    _patch_upstream(monkeypatch, handler)
    body = client.get("/api/options/llm/backend").json()
    assert body["backend"] == "vllm"
    # The budget map is exposed for visibility.
    assert body["budgets"] == {
        "none": 0, "quick": 128, "low": 256, "medium": 512, "high": 1024, "very_high": 2048, "max": 4096,
    }
    llm_backend.clear_cache()


def test_llm_backend_endpoint_unknown_when_unconfigured(client):
    from app.services import llm_backend

    llm_backend.clear_cache()
    client.patch("/api/options/llm", json={"baseUrl": ""})
    body = client.get("/api/options/llm/backend").json()
    assert body["backend"] == "unknown"


def test_refresh_for_config_probes_stored_endpoint(client, db_session, monkeypatch):
    """The poller's refresh re-detects the configured engine (single iteration)."""
    import httpx

    from app.services import llm_backend
    from app.services.llm_backend import InferenceBackend

    llm_backend.clear_cache()
    client.patch("/api/options/llm", json={"baseUrl": "http://localhost:8080/v1"})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/props":
            return httpx.Response(200, json={"total_slots": 4})
        return httpx.Response(404)

    _patch_upstream(monkeypatch, handler)
    assert llm_backend.refresh_for_config(db_session) == InferenceBackend.LLAMACPP
    llm_backend.clear_cache()


def test_poll_backend_runs_one_iteration_and_stops():
    """The lifespan poller calls the refresh and exits cleanly once stopped."""
    import asyncio

    from app import main

    stop = asyncio.Event()
    calls = {"n": 0}

    def fake_refresh() -> None:
        calls["n"] += 1
        stop.set()  # ask the loop to exit after this iteration

    original = main._refresh_backend_once
    main._refresh_backend_once = fake_refresh
    try:
        asyncio.run(main._poll_backend(stop))
    finally:
        main._refresh_backend_once = original
    assert calls["n"] == 1


# ---- Writing-agent prompts -------------------------------------------------


def test_get_returns_prompt_catalog_and_empty_overrides(client):
    """The catalog offers exactly the prompts an agent actually reads.

    `director.who_is_up` and `director.rerank` are deliberately absent: `planner_agent`
    makes the real per-beat decision and those two are called only from their own unit
    tests. A catalog row for a prompt nothing consumes teaches the author that editing
    prompts does nothing, which costs far more than the missing row.
    """
    prompts = client.get("/api/options").json()["prompts"]
    keys = {spec["key"] for spec in prompts["catalog"]}
    assert keys == {
        "character.output_contract",
        # The whole-turn writer, used when a scene runs on continuous flow.
        "scene_script.system",
        "narrator.system",
        "narrator.system_long",
        "director.branch",
        "director.pov_branch",
        "planner.system",
        "ghostwriter.line",
        "recap.summarize",
    }
    assert "director.who_is_up" not in keys
    assert "director.rerank" not in keys
    # Each catalog entry carries display metadata + default text.
    first = prompts["catalog"][0]
    assert first["agent"] and first["label"] and first["description"] and first["default"].strip()
    assert prompts["overrides"] == {}


def test_patch_prompts_sets_and_clears_override(client):
    patched = client.patch(
        "/api/options/prompts",
        json={"overrides": {"narrator.system": "Be terse and grim."}},
    ).json()
    assert patched["overrides"] == {"narrator.system": "Be terse and grim."}
    # Persists across a fresh GET.
    assert client.get("/api/options").json()["prompts"]["overrides"] == {
        "narrator.system": "Be terse and grim."
    }
    # A blank value clears the key (reverts to default).
    cleared = client.patch(
        "/api/options/prompts", json={"overrides": {"narrator.system": "  "}}
    ).json()
    assert "narrator.system" not in cleared["overrides"]


def test_patch_prompts_ignores_unknown_keys(client):
    patched = client.patch(
        "/api/options/prompts", json={"overrides": {"bogus.key": "x"}}
    ).json()
    assert patched["overrides"] == {}


# ---- max-context-tokens setting --------------------------------------------


def test_patch_llm_max_context_tokens(client):
    patched = client.patch("/api/options/llm", json={"maxContextTokens": 32768}).json()
    assert patched["maxContextTokens"] == 32768
    # Persists across a fresh GET.
    assert client.get("/api/options").json()["llm"]["maxContextTokens"] == 32768
    # Clamped to a floor of 1024.
    assert (
        client.patch("/api/options/llm", json={"maxContextTokens": 100}).json()["maxContextTokens"]
        == 1024
    )


def test_get_options_returns_default_max_context_tokens(client):
    body = client.get("/api/options").json()
    assert body["llm"]["maxContextTokens"] == 16384


# ---- context-window endpoint -----------------------------------------------


def test_context_window_detected_source(client, monkeypatch):
    import httpx

    from app.services import llm, llm_backend

    llm_backend.clear_cache()
    client.patch("/api/options/llm", json={"baseUrl": "http://localhost:8080/v1"})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            return httpx.Response(404, text="not found")
        if request.url.path == "/props":
            return httpx.Response(
                200,
                json={"total_slots": 2, "default_generation_settings": {"n_ctx": 8192}},
            )
        return httpx.Response(404, text="not found")

    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(llm, "get_http_client", factory)
    body = client.get("/api/options/llm/context-window").json()
    assert body["maxContextTokens"] == 8192
    assert body["source"] == "detected"
    llm_backend.clear_cache()


def test_context_window_configured_fallback(client, monkeypatch):
    from app.services import llm_backend

    llm_backend.clear_cache()
    # No base URL → engine cannot be probed → falls back to configured value.
    client.patch("/api/options/llm", json={"baseUrl": "", "maxContextTokens": 4096})
    body = client.get("/api/options/llm/context-window").json()
    assert body["maxContextTokens"] == 4096
    assert body["source"] == "configured"
    llm_backend.clear_cache()


def test_an_override_stored_for_a_hidden_key_still_round_trips(client):
    """Hidden means "not offered", never "not resolvable". A value saved before a key was
    hidden must not silently vanish from the payload that round-trips it."""
    client.patch("/api/options/prompts", json={"overrides": {"director.who_is_up": "Custom."}})
    prompts = client.get("/api/options").json()["prompts"]
    assert prompts["overrides"]["director.who_is_up"] == "Custom."
    # …and it is still not offered for editing.
    assert "director.who_is_up" not in {s["key"] for s in prompts["catalog"]}



def test_the_scene_preset_catalogue_is_empty_but_the_route_still_answers(client):
    """All four presets were defined purely in terms of `maxTurns` and `beatLength`.

    Both controls were removed on 2026-08-24 — pacing is the scene's judgement now — which
    left a preset with nothing to name. The route is kept and returns `[]` so no client
    404s, and the composer's picker already hid itself on an empty list.
    """
    resp = client.get("/api/options/scene-presets")
    assert resp.status_code == 200
    assert resp.json() == []


def test_every_preset_validates_against_scenario_update(client):
    """The test that stops the table drifting out of the bounds it has to live inside.

    A preset is applied by writing its values through the ordinary scenario update, so a
    value the update schema would reject is a preset that silently does nothing.
    """
    from app.schemas.scenario import ScenarioUpdate

    for p in client.get("/api/options/scene-presets").json():
        resolved = ScenarioUpdate(**p["values"])
        assert resolved.max_turns == p["values"]["maxTurns"]
        assert resolved.suggestions_count == p["values"]["suggestionsCount"]
        assert resolved.beat_length == p["values"]["beatLength"]


def test_presets_are_recognisably_different_from_the_defaults(client):
    """A preset that lands one step from the default teaches the player nothing."""
    defaults = {"maxTurns": 5, "suggestionsCount": 4, "beatLength": "medium"}
    seen = []
    for p in client.get("/api/options/scene-presets").json():
        assert p["values"] != defaults
        assert p["values"] not in seen  # and from each other
        seen.append(p["values"])
