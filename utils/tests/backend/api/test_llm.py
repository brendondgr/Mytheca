"""LLM proxy endpoints — model listing + connection test, with a mock upstream.

No real network: ``app.services.llm.get_http_client`` is patched to return an
``httpx.Client`` backed by an ``httpx.MockTransport`` that asserts the request
and returns a canned OpenAI-compatible payload.
"""

from __future__ import annotations

import httpx

from app.services import llm


def _patch_upstream(monkeypatch, handler):
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(llm, "get_http_client", factory)


def test_list_models_parses_data_ids(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == "http://localhost:7070/v1/models"
        assert request.headers["Authorization"] == "Bearer sk-test"
        return httpx.Response(200, json={"data": [{"id": "llama-3.1-8b"}, {"id": "qwen2.5"}]})

    _patch_upstream(monkeypatch, handler)
    res = client.post(
        "/api/options/llm/models",
        json={"baseUrl": "http://localhost:7070/v1", "apiKey": "sk-test"},
    )
    assert res.status_code == 200
    assert res.json()["models"] == ["llama-3.1-8b", "qwen2.5"]


def test_test_chat_returns_ok_and_sample(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url).endswith("/chat/completions")
        return httpx.Response(200, json={"choices": [{"message": {"content": " ok "}}]})

    _patch_upstream(monkeypatch, handler)
    res = client.post(
        "/api/options/llm/test",
        json={"baseUrl": "http://localhost:7070/v1", "model": "llama-3.1-8b"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["model"] == "llama-3.1-8b"
    assert data["sample"] == "ok"
    assert data["latencyMs"] >= 0


def test_upstream_error_maps_to_envelope(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="kaboom")

    _patch_upstream(monkeypatch, handler)
    res = client.post(
        "/api/options/llm/models", json={"baseUrl": "http://localhost:7070/v1"}
    )
    assert res.status_code == 502
    assert res.json()["error"]["code"] == "upstream_error"


def test_transport_error_maps_to_bad_gateway(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    _patch_upstream(monkeypatch, handler)
    res = client.post(
        "/api/options/llm/models", json={"baseUrl": "http://localhost:7070/v1"}
    )
    assert res.status_code == 502
    assert res.json()["error"]["code"] == "bad_gateway"


def test_missing_base_url_is_bad_request(client, monkeypatch):
    # No stored config and no baseUrl in the request → 400 (clear any seeded default).
    client.patch("/api/options/llm", json={"baseUrl": ""})
    _patch_upstream(monkeypatch, lambda req: httpx.Response(200, json={"data": []}))
    res = client.post("/api/options/llm/models", json={})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "bad_request"
