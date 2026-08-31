"""Streaming, one dialect at a time.

`test_llm_streaming.py` covers the streaming transport's behaviour on the
OpenAI-compatible route — deltas, fallbacks, the reasoning splitter, usage. This
file covers the thing that route cannot show: that `llm.chat_complete_stream`
reads a stream through the ACTIVE ADAPTER rather than through one hardcoded
dialect.

Every failure this guards against is silent. An unrecognised media type is
indistinguishable from an endpoint that refuses to stream, so the reader falls
back to blocking and logs nothing; an unread `usage` frame blanks the player's
context dial with no error; the wrong auth header is a 401 that reads exactly
like a bad key. None of them raise, and none of them are visible in a transcript
after the fact.

**What these tests do NOT establish.** They are fakes, built from each
provider's reference documentation. `anthropic`, `gemini` and `ollama` have
still never streamed from a live endpoint — see `docs/checklist.md`. A test
written from the same document as the code cannot catch the two of them being
wrong together.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.services import llm, llm_backend, llm_providers

BASE = "http://endpoint.test/v1"


@pytest.fixture(autouse=True)
def _clean():
    """Reset both caches AND the process-global provider around every test.

    `_NO_STREAM` is keyed on `(base_url, model)` and not on the provider, so one
    test's refusal would silently send the next test's call down the blocking
    path — where it would pass for the wrong reason.
    """
    before = llm_providers.active_provider()
    llm_backend.clear_cache()
    llm._NO_STREAM.clear()
    yield
    llm_providers.set_active(before)
    llm_backend.clear_cache()
    llm._NO_STREAM.clear()


def _serve(monkeypatch, body: str, content_type: str, captured: dict | None = None):
    """Answer the engine probes with 404s and the completion POST with `body`."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404, json={"detail": "Not Found"})
        if captured is not None:
            captured["url"] = str(request.url)
            captured["headers"] = dict(request.headers)
            captured["body"] = json.loads(request.content)
        return httpx.Response(200, text=body, headers={"content-type": content_type})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _drain(gen):
    deltas = []
    try:
        while True:
            deltas.append(next(gen))
    except StopIteration as stop:
        return deltas, stop.value


def _sse(*payloads: dict) -> str:
    return "".join(f"data: {json.dumps(p)}\n\n" for p in payloads)


def _stream(model: str = "m", **kw):
    return llm.chat_complete_stream(BASE, "key", model, [{"role": "user", "content": "hi"}], **kw)


# ---- Anthropic --------------------------------------------------------------
#
# Named SSE events, no `[DONE]`, input tokens reported ONCE at `message_start`.


def _anthropic_stream() -> str:
    return _sse(
        {"type": "message_start", "message": {"usage": {"input_tokens": 40, "cache_read_input_tokens": 10}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "The tide "}},
        {"type": "ping"},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "turns."}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 4}},
        {"type": "message_stop"},
    )


def test_anthropic_text_deltas_are_read(monkeypatch):
    llm_providers.set_active("anthropic")
    _serve(monkeypatch, _anthropic_stream(), "text/event-stream")

    deltas, (text, prompt_tokens) = _drain(_stream())

    assert text == "The tide turns."
    # Two text frames, not one blob: `ping`, `content_block_start` and
    # `content_block_stop` carry no text and must not yield empty deltas.
    assert [d.answer for d in deltas] == ["The tide ", "turns."]
    # 40 input + 10 cache read. Anthropic's cache counts are ADDITIVE, unlike
    # OpenAI's subset-of-prompt_tokens, and `parse_usage` owns that arithmetic.
    assert prompt_tokens == 50


def test_anthropic_thinking_reaches_the_reasoning_channel_not_the_prose(monkeypatch):
    """The one place a wrong answer would be printed to the player."""
    llm_providers.set_active("anthropic")
    _serve(
        monkeypatch,
        _sse(
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "thinking_delta", "thinking": "she is lying"}},
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "signature_delta", "signature": "AbC123=="}},
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "text_delta", "text": "I believe you."}},
            {"type": "message_stop"},
        ),
        "text/event-stream",
    )

    deltas, (text, _) = _drain(_stream())

    assert text == "I believe you."
    assert "".join(d.reasoning for d in deltas) == "she is lying"
    # The provenance token is neither prose nor thought; base64 in the thinking
    # pane is as wrong as base64 in the scene.
    assert "AbC123" not in "".join(d.reasoning + d.answer for d in deltas)


def test_anthropic_authenticates_with_x_api_key(monkeypatch):
    """A Bearer token here is a 401 that reads like a bad key."""
    llm_providers.set_active("anthropic")
    seen: dict = {}
    _serve(monkeypatch, _anthropic_stream(), "text/event-stream", captured=seen)

    _drain(_stream())

    assert seen["headers"].get("x-api-key") == "key"
    assert "authorization" not in seen["headers"]
    assert seen["body"]["stream"] is True


def test_anthropic_stops_at_message_stop_without_a_done_sentinel(monkeypatch):
    """Anything after the terminator is not part of the reply."""
    llm_providers.set_active("anthropic")
    _serve(
        monkeypatch,
        _sse(
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "text_delta", "text": "done"}},
            {"type": "message_stop"},
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "text_delta", "text": " EXTRA"}},
        ),
        "text/event-stream",
    )

    _, (text, _) = _drain(_stream())

    assert text == "done"


# ---- Gemini -----------------------------------------------------------------
#
# Every frame is a whole GenerateContentResponse; the LAST one carries prose.


def test_gemini_frames_are_read_including_the_terminal_one(monkeypatch):
    llm_providers.set_active("gemini")
    _serve(
        monkeypatch,
        _sse(
            {"candidates": [{"content": {"parts": [{"text": "Salt "}]}}],
             "usageMetadata": {"promptTokenCount": 12}},
            {"candidates": [{"content": {"parts": [{"text": "and smoke."}]},
                             "finishReason": "STOP"}],
             "usageMetadata": {"promptTokenCount": 12, "cachedContentTokenCount": 4}},
        ),
        "text/event-stream",
    )

    _, (text, prompt_tokens) = _drain(_stream())

    # "and smoke." rides on the frame that also says `finishReason`. A loop that
    # checks `stream_done` before reading the frame loses the last sentence of
    # every Gemini turn — and loses it in a way that reads as the model
    # trailing off, not as a bug.
    assert text == "Salt and smoke."
    assert prompt_tokens == 12


def test_gemini_thought_parts_do_not_become_prose(monkeypatch):
    llm_providers.set_active("gemini")
    _serve(
        monkeypatch,
        _sse(
            {"candidates": [{"content": {"parts": [
                {"text": "weigh the options", "thought": True},
                {"text": "Very well."},
            ]}, "finishReason": "STOP"}]},
        ),
        "text/event-stream",
    )

    deltas, (text, _) = _drain(_stream())

    assert text == "Very well."
    assert "".join(d.reasoning for d in deltas) == "weigh the options"


def test_gemini_asks_the_streaming_url_and_the_key_never_enters_it(monkeypatch):
    """Gemini selects the stream in the PATH, not with `"stream": true`."""
    llm_providers.set_active("gemini")
    seen: dict = {}
    _serve(
        monkeypatch,
        _sse({"candidates": [{"content": {"parts": [{"text": "x"}]}, "finishReason": "STOP"}]}),
        "text/event-stream",
        captured=seen,
    )

    _drain(_stream(model="gemini-3-pro"))

    assert ":streamGenerateContent" in seen["url"] and "alt=sse" in seen["url"]
    # A credential in a query string ends up in access logs and proxy caches.
    assert "key" not in httpx.URL(seen["url"]).params
    assert seen["headers"].get("x-goog-api-key") == "key"


# ---- Ollama -----------------------------------------------------------------
#
# NDJSON, not SSE. The closing frame has EMPTY content and the only token count.


def _ndjson(*rows: dict) -> str:
    return "".join(json.dumps(r) + "\n" for r in rows)


def test_ollama_ndjson_is_a_stream_even_though_it_is_not_sse(monkeypatch):
    llm_providers.set_active("ollama")
    _serve(
        monkeypatch,
        _ndjson(
            {"message": {"role": "assistant", "content": "A door "}, "done": False},
            {"message": {"role": "assistant", "content": "opens."}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True,
             "done_reason": "stop", "prompt_eval_count": 31},
        ),
        "application/x-ndjson",
    )

    deltas, (text, prompt_tokens) = _drain(_stream())

    # The media check is the whole test: insisting on `text/event-stream` here
    # rejects a perfectly good stream, falls back to blocking, and says nothing.
    assert text == "A door opens."
    assert [d.answer for d in deltas] == ["A door ", "opens."]
    # Carried only by the closing frame, which a reader that breaks on `done`
    # before reading the frame never sees.
    assert prompt_tokens == 31


def test_ollama_thinking_is_its_own_channel(monkeypatch):
    llm_providers.set_active("ollama")
    _serve(
        monkeypatch,
        _ndjson(
            {"message": {"content": "", "thinking": "who is asking"}, "done": False},
            {"message": {"content": "Nobody."}, "done": False},
            {"message": {"content": ""}, "done": True, "prompt_eval_count": 9},
        ),
        "application/x-ndjson",
    )

    deltas, (text, _) = _drain(_stream())

    assert text == "Nobody."
    assert "".join(d.reasoning for d in deltas) == "who is asking"


def test_ollama_reports_no_cache_figure_rather_than_zero(monkeypatch):
    """Ollama never says how much prefix it reused; "unknown" is not "none"."""
    llm_providers.set_active("ollama")
    usage: dict = {}
    _serve(
        monkeypatch,
        _ndjson({"message": {"content": "hi"}, "done": True, "prompt_eval_count": 7}),
        "application/x-ndjson",
    )

    _drain(_stream(usage_out=usage))

    assert usage == {"prompt_tokens": 7, "cached_tokens": None}


# ---- Cross-cutting ----------------------------------------------------------


def test_every_adapter_claims_a_dispatched_stream(monkeypatch):
    """The flag the Options picker renders must match what this loop can do.

    It stays on the contract rather than being deleted with the branch it fed:
    a fifth adapter that can only stream through an SDK declares `False` and the
    picker warns, instead of an operator discovering it mid-scene.
    """
    for provider in ("openai-compatible", "anthropic", "gemini", "ollama"):
        adapter = llm_providers.get_adapter(provider)
        assert adapter.streaming_dispatched is True, provider
        assert adapter.stream_media_types, provider


def test_a_wrong_media_type_falls_back_to_blocking_rather_than_hanging(monkeypatch):
    """The failure that used to happen to three providers out of four."""
    llm_providers.set_active("anthropic")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404, json={"detail": "Not Found"})
        if "stream" in json.loads(request.content):
            # Answers with plain JSON under a 200 — not the stream we asked for.
            return httpx.Response(
                200,
                json={"content": [{"type": "text", "text": "whole thing"}],
                      "usage": {"input_tokens": 5}},
                headers={"content-type": "application/json"},
            )
        return httpx.Response(200, json={"content": [{"type": "text", "text": "whole thing"}],
                                         "usage": {"input_tokens": 5}})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )

    deltas, (text, _) = _drain(_stream())

    assert text == "whole thing"
    assert [d.answer for d in deltas] == ["whole thing"]
    # Remembered, so the next call does not pay for a failed attempt again.
    assert (llm._normalize(BASE), "m") in llm._NO_STREAM


def test_a_stop_sequence_survives_reasoning_where_the_provider_separates_them(monkeypatch):
    """`stop_is_safe` was a constant; it is a property of the engine.

    llama.cpp matches a stop sequence against the hidden channel and kills the
    generation mid-thought, which is why the OpenAI-compatible adapter answers
    False here at any effort but NONE. Anthropic puts deliberation in its own
    block and documents `stop_sequences` against the response text.
    """
    from app.schemas.reasoning import ReasoningEffort

    llm_providers.set_active("openai-compatible")
    assert llm.stop_is_safe(ReasoningEffort.HIGH) is False
    assert llm.stop_is_safe(ReasoningEffort.NONE) is True

    llm_providers.set_active("anthropic")
    assert llm.stop_is_safe(ReasoningEffort.HIGH) is True
