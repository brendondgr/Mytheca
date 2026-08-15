"""`services.llm` fits the requested output tokens into the model's context window.

The operator's saved Max tokens is an *output* budget, but the server counts prompt +
completion against one window: a 48000-token setting on a 48000-token model 400s on
every call (the character-draft 502). The generation path learns the window from that
400, clamps, and retries once — and clamps up-front on later calls. LLM is offline via
httpx.MockTransport.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.errors import APIError
from app.schemas.settings import LlmParams
from app.services import llm

_OVERFLOW = {
    "error": {
        "message": (
            "This model's maximum context length is 48000 tokens. However, you "
            "requested 48000 output tokens and your prompt contains 1331 characters."
        )
    }
}


@pytest.fixture(autouse=True)
def _clear_learned_limits():
    llm._CONTEXT_LIMITS.clear()
    yield
    llm._CONTEXT_LIMITS.clear()


def _patch(monkeypatch, handler):
    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _call(max_tokens: int = 48000) -> str:
    return llm.chat_complete(
        "http://localhost:7070/v1",
        "sk-test",
        "m",
        [{"role": "user", "content": "hi"}],
        LlmParams(max_tokens=max_tokens),
    )


def test_retries_once_with_a_fitted_budget_after_a_context_overflow(monkeypatch):
    seen: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        import json

        seen.append(json.loads(req.content)["max_tokens"])
        if len(seen) == 1:
            return httpx.Response(400, json=_OVERFLOW)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Drafted."}}]})

    _patch(monkeypatch, handler)
    assert _call() == "Drafted."
    assert seen[0] == 48000
    assert 0 < seen[1] < 48000


def test_learned_limit_clamps_the_next_call_before_sending(monkeypatch):
    seen: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        import json

        seen.append(json.loads(req.content)["max_tokens"])
        if len(seen) == 1:
            return httpx.Response(400, json=_OVERFLOW)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Drafted."}}]})

    _patch(monkeypatch, handler)
    _call()
    _call()
    assert len(seen) == 3  # overflow + retry + one already-clamped call
    assert seen[2] == seen[1]


def test_a_budget_that_already_fits_is_left_alone(monkeypatch):
    seen: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        import json

        seen.append(json.loads(req.content)["max_tokens"])
        if len(seen) == 1:
            return httpx.Response(400, json=_OVERFLOW)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Drafted."}}]})

    _patch(monkeypatch, handler)
    _call()
    _call(max_tokens=8192)
    assert seen[-1] == 8192


def test_prompt_longer_than_the_window_is_a_clear_error(monkeypatch):
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json=_OVERFLOW)

    _patch(monkeypatch, handler)
    with pytest.raises(APIError) as exc:
        llm.chat_complete(
            "http://localhost:7070/v1",
            "sk-test",
            "m",
            [{"role": "user", "content": "x" * (48000 * 4)}],
            LlmParams(max_tokens=8192),
        )
    assert "context window" in exc.value.message


def test_a_non_context_400_still_surfaces_as_upstream_error(monkeypatch):
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "unknown model"}})

    _patch(monkeypatch, handler)
    with pytest.raises(APIError) as exc:
        _call()
    assert exc.value.status_code == 502
