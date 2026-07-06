"""Inference-engine detection + reasoning-budget injection.

No real network: ``app.services.llm.get_http_client`` is patched to an
``httpx.MockTransport`` that answers the ``/version`` (vLLM) and ``/props``
(llama.cpp) probes, mirroring ``test_llm.py``.
"""

from __future__ import annotations

import httpx
import pytest

from app.schemas.reasoning import THINKING_BUDGET, ReasoningEffort, budget_for
from app.services import llm, llm_backend
from app.services.llm_backend import InferenceBackend


@pytest.fixture(autouse=True)
def _clear_detection_cache():
    llm_backend.clear_cache()
    yield
    llm_backend.clear_cache()


def _patch_upstream(monkeypatch, handler):
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(llm, "get_http_client", factory)


def _vllm_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/version":
        return httpx.Response(200, json={"version": "0.21.0"})
    return httpx.Response(404, text="not found")


def _llamacpp_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/version":
        return httpx.Response(404, text="not found")
    if request.url.path == "/props":
        return httpx.Response(200, json={"total_slots": 4, "chat_template": "..."})
    return httpx.Response(404, text="not found")


# ---- detection -------------------------------------------------------------


def test_detect_vllm_via_version(monkeypatch):
    _patch_upstream(monkeypatch, _vllm_handler)
    assert detect("http://localhost:8000/v1") == InferenceBackend.VLLM


def test_detect_llamacpp_via_props(monkeypatch):
    _patch_upstream(monkeypatch, _llamacpp_handler)
    assert detect("http://localhost:8080/v1") == InferenceBackend.LLAMACPP


def test_detect_unknown_when_neither(monkeypatch):
    _patch_upstream(monkeypatch, lambda req: httpx.Response(404, text="nope"))
    assert detect("http://localhost:9999/v1") == InferenceBackend.UNKNOWN


def test_detect_blank_url_is_unknown(monkeypatch):
    _patch_upstream(monkeypatch, lambda req: httpx.Response(200, json={"version": "x"}))
    assert detect("") == InferenceBackend.UNKNOWN


def test_probe_strips_v1_suffix(monkeypatch):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"version": "1"}) if request.url.path == "/version" else httpx.Response(404)

    _patch_upstream(monkeypatch, handler)
    detect("http://localhost:8000/v1/")
    # The /v1 (and trailing slash) is stripped — probes hit the server root.
    assert "/version" in seen
    assert all("/v1/" not in p for p in seen)


def detect(url: str) -> InferenceBackend:
    return llm_backend.detect_backend(url, "")


# ---- TTL cache -------------------------------------------------------------


def test_get_backend_caches_within_ttl(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            calls["n"] += 1
            return httpx.Response(200, json={"version": "0.21.0"})
        return httpx.Response(404)

    _patch_upstream(monkeypatch, handler)
    first = llm_backend.get_backend("http://localhost:8000/v1")
    probes_after_first = calls["n"]
    second = llm_backend.get_backend("http://localhost:8000/v1")
    assert first == second == InferenceBackend.VLLM
    # The second call is served from cache — no additional /version probe.
    assert calls["n"] == probes_after_first


def test_get_backend_force_reprobes(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            calls["n"] += 1
            return httpx.Response(200, json={"version": "0.21.0"})
        return httpx.Response(404)

    _patch_upstream(monkeypatch, handler)
    llm_backend.get_backend("http://localhost:8000/v1")
    before = calls["n"]
    llm_backend.get_backend("http://localhost:8000/v1", force=True)
    assert calls["n"] == before + 1


# ---- budget injection ------------------------------------------------------


def test_apply_reasoning_vllm_key():
    body = llm_backend.apply_reasoning({}, InferenceBackend.VLLM, ReasoningEffort.LOW)
    assert body == {"thinking_token_budget": 256}


def test_apply_reasoning_llamacpp_key():
    body = llm_backend.apply_reasoning({}, InferenceBackend.LLAMACPP, ReasoningEffort.MEDIUM)
    assert body == {"thinking_budget_tokens": 512}


def test_apply_reasoning_unknown_is_noop():
    body = llm_backend.apply_reasoning({"model": "x"}, InferenceBackend.UNKNOWN, ReasoningEffort.MAX)
    assert body == {"model": "x"}


def test_budget_map_matches_spec():
    assert THINKING_BUDGET == {
        ReasoningEffort.LOW: 256,
        ReasoningEffort.MEDIUM: 512,
        ReasoningEffort.HIGH: 1024,
        ReasoningEffort.VERY_HIGH: 2048,
        ReasoningEffort.MAX: 4096,
    }
    assert budget_for(ReasoningEffort.HIGH) == 1024


# ---- context-window probe --------------------------------------------------


def _llamacpp_with_ctx_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/version":
        return httpx.Response(404, text="not found")
    if request.url.path == "/props":
        return httpx.Response(
            200,
            json={
                "total_slots": 4,
                "default_generation_settings": {"n_ctx": 8192},
            },
        )
    return httpx.Response(404, text="not found")


def _llamacpp_top_level_ctx_handler(request: httpx.Request) -> httpx.Response:
    """llama.cpp props without default_generation_settings — falls back to top-level n_ctx."""
    if request.url.path == "/version":
        return httpx.Response(404, text="not found")
    if request.url.path == "/props":
        return httpx.Response(200, json={"total_slots": 2, "n_ctx": 4096})
    return httpx.Response(404, text="not found")


def _vllm_with_ctx_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/version":
        return httpx.Response(200, json={"version": "0.21.0"})
    if request.url.path.rstrip("/").endswith("/models"):
        return httpx.Response(
            200,
            json={"data": [{"id": "meta-llama-3-8b", "max_model_len": 131072}]},
        )
    return httpx.Response(404, text="not found")


def test_get_context_window_llamacpp_default_generation_settings(monkeypatch):
    _patch_upstream(monkeypatch, _llamacpp_with_ctx_handler)
    assert llm_backend.get_context_window("http://localhost:8080/v1") == 8192


def test_get_context_window_llamacpp_top_level_n_ctx_fallback(monkeypatch):
    _patch_upstream(monkeypatch, _llamacpp_top_level_ctx_handler)
    assert llm_backend.get_context_window("http://localhost:8080/v1") == 4096


def test_get_context_window_vllm_max_model_len(monkeypatch):
    _patch_upstream(monkeypatch, _vllm_with_ctx_handler)
    assert llm_backend.get_context_window("http://localhost:8000/v1") == 131072


def test_get_context_window_unknown_backend_returns_none(monkeypatch):
    _patch_upstream(monkeypatch, lambda req: httpx.Response(404, text="nope"))
    assert llm_backend.get_context_window("http://localhost:9999/v1") is None


def test_get_context_window_blank_url_returns_none(monkeypatch):
    _patch_upstream(monkeypatch, _vllm_with_ctx_handler)
    assert llm_backend.get_context_window("") is None


def test_get_context_window_error_returns_none(monkeypatch):
    def error_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    _patch_upstream(monkeypatch, error_handler)
    assert llm_backend.get_context_window("http://localhost:8000/v1") is None
