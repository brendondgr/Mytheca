"""The recap agent — what the scene remembers after the window forgets it.

Best-effort by design: every failure path returns ``None`` and the caller keeps whatever it
had. A scene that cannot summarise forgets a little more than one that can; it does not fail.
"""

from __future__ import annotations

import httpx

from app.agents import prompt_registry, recap_agent
from app.schemas.settings import LlmParams

CONN = ("http://localhost:7070/v1", "sk-test", "test-model", LlmParams())


def _patch(monkeypatch, handler):
    from app.services import llm

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _ok(content: str, capture: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        # Path-aware: the engine probe issues GETs to /version and /props, and a handler that
        # asserts on POST bodies unconditionally fails in isolation while passing in the full
        # suite (the probe result is cached). See the repo's known engine-probe flake.
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        if capture is not None:
            capture["body"] = request.content.decode()
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return handler


def test_it_folds_beats_into_a_summary(monkeypatch):
    capture: dict = {}
    _patch(monkeypatch, _ok("Mei confessed. The lamp went over.", capture))
    out = recap_agent.summarize_history(CONN, beats=["Mei confessed.", "The lamp went over."])
    assert out == "Mei confessed. The lamp went over."
    assert "The lamp went over." in capture["body"]


def test_it_is_incremental_and_shows_the_model_what_is_already_remembered(monkeypatch):
    """The cost argument: each call adds the newly-dropped beats to the previous summary
    rather than re-reading the whole scene, so a long session costs one call per anchor
    block instead of a growing re-summarisation every turn."""
    capture: dict = {}
    _patch(monkeypatch, _ok("Updated.", capture))
    recap_agent.summarize_history(
        CONN, previous_summary="Mei arrived at the harbour.", beats=["She left again."]
    )
    body = capture["body"]
    assert "Mei arrived at the harbour." in body
    assert "She left again." in body
    assert "already remember" in body


def test_an_api_error_returns_none_rather_than_raising(monkeypatch):
    def boom(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        return httpx.Response(500, json={"error": "down"})

    _patch(monkeypatch, boom)
    assert recap_agent.summarize_history(CONN, beats=["Something happened."]) is None


def test_an_empty_reply_returns_none(monkeypatch):
    _patch(monkeypatch, _ok("   "))
    assert recap_agent.summarize_history(CONN, beats=["Something happened."]) is None


def test_no_endpoint_returns_none_without_calling_anything(monkeypatch):
    def never(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no call should be made without a base URL")

    _patch(monkeypatch, never)
    conn = ("", "", "test-model", LlmParams())
    assert recap_agent.summarize_history(conn, beats=["x"]) is None


def test_no_beats_returns_none_without_calling_anything(monkeypatch):
    def never(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no call should be made with nothing to fold")

    _patch(monkeypatch, never)
    assert recap_agent.summarize_history(CONN, beats=[]) is None
    assert recap_agent.summarize_history(CONN, beats=["", "   "]) is None


def test_a_runaway_summary_is_capped(monkeypatch):
    """A summary that grew without bound would eventually cost more context than the beats it
    replaced, defeating the whole point."""
    _patch(monkeypatch, _ok("x" * 10_000))
    out = recap_agent.summarize_history(CONN, beats=["x"])
    assert out is not None and len(out) <= recap_agent.MAX_SUMMARY_CHARS


def test_the_cap_prefers_a_paragraph_boundary(monkeypatch):
    """A summary cut mid-sentence reads as corruption to whatever model reads it next."""
    para = "y" * 2_000
    _patch(monkeypatch, _ok(f"{para}\n\n{'z' * 2_000}"))
    out = recap_agent.summarize_history(CONN, beats=["x"])
    assert out == para


def test_an_author_override_replaces_the_system_prompt(monkeypatch):
    capture: dict = {}
    _patch(monkeypatch, _ok("Fine.", capture))
    recap_agent.summarize_history(CONN, beats=["x"], system="REMEMBER IN LIMERICKS.")
    import json

    system = json.loads(capture["body"])["messages"][0]["content"]
    assert system.startswith("REMEMBER IN LIMERICKS.")


def test_it_falls_back_to_the_registry_default(monkeypatch):
    capture: dict = {}
    _patch(monkeypatch, _ok("Fine.", capture))
    recap_agent.summarize_history(CONN, beats=["x"])
    import json

    system = json.loads(capture["body"])["messages"][0]["content"]
    assert system.startswith(prompt_registry.default(prompt_registry.RECAP_SUMMARIZE)[:40])
