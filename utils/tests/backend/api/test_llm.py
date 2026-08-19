"""LLM proxy endpoints — model listing + connection test, with a mock upstream.

No real network: ``app.services.llm.get_http_client`` is patched to return an
``httpx.Client`` backed by an ``httpx.MockTransport`` that asserts the request
and returns a canned OpenAI-compatible payload.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.schemas.reasoning import ReasoningEffort
from app.services import llm, llm_backend


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


# ---- reasoning-budget injection in chat_complete ---------------------------


@pytest.fixture(autouse=True)
def _clear_detection_cache():
    llm_backend.clear_cache()
    yield
    llm_backend.clear_cache()


def _chat_body(captured: dict, engine: str):
    """A handler that answers the engine probe and captures the /chat body."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/version":
            return (
                httpx.Response(200, json={"version": "0.21.0"})
                if engine == "vllm"
                else httpx.Response(404)
            )
        if path == "/props":
            return (
                httpx.Response(200, json={"total_slots": 2})
                if engine == "llamacpp"
                else httpx.Response(404)
            )
        if path.endswith("/chat/completions"):
            captured.update(json.loads(request.content.decode()))
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
        return httpx.Response(404)

    return handler


def test_chat_complete_injects_vllm_budget(monkeypatch):
    captured: dict = {}
    _patch_upstream(monkeypatch, _chat_body(captured, "vllm"))
    llm.chat_complete(
        "http://localhost:8000/v1", "", "m", [{"role": "user", "content": "hi"}],
        reasoning=ReasoningEffort.LOW,
    )
    assert captured["thinking_token_budget"] == 256
    assert "thinking_budget_tokens" not in captured


def test_chat_complete_injects_llamacpp_budget(monkeypatch):
    captured: dict = {}
    _patch_upstream(monkeypatch, _chat_body(captured, "llamacpp"))
    llm.chat_complete(
        "http://localhost:8080/v1", "", "m", [{"role": "user", "content": "hi"}],
        reasoning=ReasoningEffort.MEDIUM,
    )
    assert captured["thinking_budget_tokens"] == 512
    assert "thinking_token_budget" not in captured


def test_chat_complete_no_reasoning_injects_nothing(monkeypatch):
    captured: dict = {}
    _patch_upstream(monkeypatch, _chat_body(captured, "vllm"))
    llm.chat_complete("http://localhost:8000/v1", "", "m", [{"role": "user", "content": "hi"}])
    assert "thinking_token_budget" not in captured
    assert "thinking_budget_tokens" not in captured


def test_chat_complete_unknown_engine_still_caps_the_thinking(monkeypatch):
    """An unidentified endpoint gets BOTH budget keys rather than none.

    It previously got neither, which meant the ``reasoning=`` argument was silently
    inert for any endpoint that matched no probe — the model then thought until it
    exhausted ``max_tokens`` or the generation timed out.
    """
    captured: dict = {}
    _patch_upstream(monkeypatch, _chat_body(captured, "openai"))  # neither probe matches
    llm.chat_complete(
        "http://localhost:9000/v1", "", "m", [{"role": "user", "content": "hi"}],
        reasoning=ReasoningEffort.HIGH,
    )
    assert captured["thinking_token_budget"] == 1024
    assert captured["thinking_budget_tokens"] == 1024


def test_chat_complete_merges_extra_body(monkeypatch):
    # The vLLM guided-decoding seam: extra_body is merged into the request body.
    captured: dict = {}
    _patch_upstream(monkeypatch, _chat_body(captured, "openai"))
    llm.chat_complete(
        "http://localhost:9000/v1", "", "m", [{"role": "user", "content": "hi"}],
        extra_body={"guided_choice": ["1", "2"]},
    )
    assert captured["guided_choice"] == ["1", "2"]
