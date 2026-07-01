"""Line-to-line consistency guard: verdict parse + best-effort defaults (mocked LLM)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.schemas.settings import LlmParams
from app.services import consistency, llm, llm_backend

_CONN = ("http://localhost:7070/v1", "sk-test", "test-model", LlmParams())


@pytest.fixture(autouse=True)
def _clear_detection_cache():
    llm_backend.clear_cache()
    yield
    llm_backend.clear_cache()


def _patch(monkeypatch, content: str):
    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_consistent_verdict(monkeypatch):
    _patch(monkeypatch, json.dumps({"consistent": True}))
    v = consistency.review(
        _CONN, stable_prefix="", prior="Mei: The lantern is lit.", candidate="Kira: I see the glow."
    )
    assert v.consistent is True


def test_contradiction_verdict_carries_reason(monkeypatch):
    _patch(monkeypatch, json.dumps({"consistent": False, "reason": "the lantern was just lit"}))
    v = consistency.review(
        _CONN,
        stable_prefix="",
        prior="Mei: The lantern is lit.",
        candidate="Kira: The lantern is dark.",
    )
    assert v.consistent is False and "lantern" in v.reason


def test_empty_prior_or_candidate_short_circuits_without_llm(monkeypatch):
    def boom():  # the guard must not call the model when there is nothing to compare
        raise AssertionError("consistency should not call the LLM here")

    monkeypatch.setattr(llm, "get_http_client", boom)
    assert consistency.review(_CONN, stable_prefix="", prior="", candidate="Kira: hi").consistent
    assert consistency.review(_CONN, stable_prefix="", prior="Mei: x", candidate="  ").consistent


def test_malformed_reply_defaults_to_consistent(monkeypatch):
    _patch(monkeypatch, "not json at all")
    v = consistency.review(_CONN, stable_prefix="", prior="Mei: x", candidate="Kira: y")
    assert v.consistent is True  # best-effort → never block the turn
