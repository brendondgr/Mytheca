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
        "low": 256, "medium": 512, "high": 1024, "very_high": 2048, "max": 4096,
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
