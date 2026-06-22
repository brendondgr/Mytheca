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
