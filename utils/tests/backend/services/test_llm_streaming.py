"""Streaming generation transport (``llm.chat_complete_stream``).

No real network: ``app.services.llm.get_http_client`` is patched to an
``httpx.MockTransport``. Handlers here are **path-aware** — the engine probe issues
``GET /version`` / ``GET /props`` / ``GET /models`` before the completion POST, and a
handler that assumes every request is the POST fails only when run in isolation (the
detection cache hides it in a full-suite run).
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.errors import APIError
from app.services import llm, llm_backend


@pytest.fixture(autouse=True)
def _clear_caches():
    llm_backend.clear_cache()
    llm._NO_STREAM.clear()
    yield
    llm_backend.clear_cache()
    llm._NO_STREAM.clear()


def _sse(*chunks: dict, done: bool = True) -> str:
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks)
    return body + ("data: [DONE]\n\n" if done else "")


def _delta(content: str | None = None, reasoning: str | None = None, finish: str | None = None) -> dict:
    d: dict = {}
    if content is not None:
        d["content"] = content
    if reasoning is not None:
        d["reasoning_content"] = reasoning
    return {"choices": [{"index": 0, "delta": d, "finish_reason": finish}]}


def _usage(prompt_tokens: int) -> dict:
    return {"choices": [], "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": 3}}


def _patch(monkeypatch, handler):
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(llm, "get_http_client", factory)


def _streaming_handler(sse_body: str, captured: dict | None = None):
    """Answer the engine probes with 404s and the completion POST with an event stream."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404, json={"detail": "Not Found"})
        if captured is not None:
            captured.update(json.loads(request.content))
        return httpx.Response(
            200, text=sse_body, headers={"content-type": "text/event-stream"}
        )

    return handler


def _drain(gen):
    """Run a generator to completion, collecting yields and its return value."""
    deltas = []
    try:
        while True:
            deltas.append(next(gen))
    except StopIteration as stop:
        return deltas, stop.value


# ---- happy path ------------------------------------------------------------


def test_streams_answer_deltas_and_returns_the_whole_text(monkeypatch):
    body = _sse(
        _delta(content="Hello"),
        _delta(content=" there"),
        _delta(content="!", finish="stop"),
        _usage(42),
    )
    _patch(monkeypatch, _streaming_handler(body))

    deltas, result = _drain(
        llm.chat_complete_stream("http://x/v1", "", "m", [{"role": "user", "content": "hi"}])
    )

    assert [d.answer for d in deltas] == ["Hello", " there", "!"]
    assert result == ("Hello there!", 42)


def test_reasoning_arrives_on_its_own_channel(monkeypatch):
    """The whole point: deliberation is separable from prose as it arrives."""
    body = _sse(
        _delta(reasoning="She is lying"),
        _delta(reasoning=" about the letter"),
        _delta(content="I believe you."),
        _usage(10),
    )
    _patch(monkeypatch, _streaming_handler(body))

    deltas, (text, _) = _drain(
        llm.chat_complete_stream("http://x/v1", "", "m", [{"role": "user", "content": "hi"}])
    )

    assert "".join(d.reasoning for d in deltas) == "She is lying about the letter"
    # Reasoning never leaks into the returned prose.
    assert text == "I believe you."


def test_inline_think_tags_are_split_out_of_content(monkeypatch):
    """Fallback for endpoints that inline their thinking instead of separating it."""
    body = _sse(
        _delta(content="<thi"),
        _delta(content="nk>plotting</think>Good "),
        _delta(content="evening."),
    )
    _patch(monkeypatch, _streaming_handler(body))

    deltas, (text, _) = _drain(
        llm.chat_complete_stream("http://x/v1", "", "m", [{"role": "user", "content": "hi"}])
    )

    assert text == "Good evening."
    assert "".join(d.reasoning for d in deltas) == "plotting"
    # A tag split across two chunks is never emitted as prose.
    assert "<thi" not in "".join(d.answer for d in deltas)


def test_sets_stream_and_requests_usage(monkeypatch):
    captured: dict = {}
    _patch(monkeypatch, _streaming_handler(_sse(_delta(content="ok")), captured))

    _drain(llm.chat_complete_stream("http://x/v1", "", "m", [{"role": "user", "content": "hi"}]))

    assert captured["stream"] is True
    assert captured["stream_options"] == {"include_usage": True}


def test_sampler_params_match_the_blocking_path(monkeypatch):
    """Both paths build the body through the same helper, so they cannot drift."""
    from app.schemas.settings import LlmParams

    captured: dict = {}
    _patch(monkeypatch, _streaming_handler(_sse(_delta(content="ok")), captured))
    params = LlmParams(temperature=0.3, max_tokens=1234, top_p=0.8)

    _drain(
        llm.chat_complete_stream(
            "http://x/v1", "", "m", [{"role": "user", "content": "hi"}], params
        )
    )

    assert captured["temperature"] == 0.3
    assert captured["max_tokens"] == 1234
    assert captured["top_p"] == 0.8


# ---- degradation -----------------------------------------------------------


def test_falls_back_to_blocking_when_the_endpoint_refuses_to_stream(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404, json={"detail": "Not Found"})
        if json.loads(request.content).get("stream"):
            return httpx.Response(400, json={"error": "streaming is not supported"})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "blocking reply"}}]}
        )

    _patch(monkeypatch, handler)

    deltas, (text, _) = _drain(
        llm.chat_complete_stream("http://x/v1", "", "m", [{"role": "user", "content": "hi"}])
    )

    assert text == "blocking reply"
    # The whole completion arrives as a single delta, so callers need no special case.
    assert [d.answer for d in deltas] == ["blocking reply"]


def test_a_refusal_is_remembered_so_the_next_call_goes_straight_to_blocking(monkeypatch):
    attempts: list[bool] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404, json={"detail": "Not Found"})
        streaming = bool(json.loads(request.content).get("stream"))
        attempts.append(streaming)
        if streaming:
            return httpx.Response(400, json={"error": "nope"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    _patch(monkeypatch, handler)
    args = ("http://x/v1", "", "m", [{"role": "user", "content": "hi"}])

    _drain(llm.chat_complete_stream(*args))
    _drain(llm.chat_complete_stream(*args))

    # One failed streaming attempt total — the second call did not retry it.
    assert attempts.count(True) == 1


def test_a_non_event_stream_response_falls_back(monkeypatch):
    """A 200 that is not actually an event stream must not be parsed as one."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404, json={"detail": "Not Found"})
        if json.loads(request.content).get("stream"):
            return httpx.Response(200, json={"choices": [{"message": {"content": "whole"}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "whole"}}]})

    _patch(monkeypatch, handler)

    _, (text, _) = _drain(
        llm.chat_complete_stream("http://x/v1", "", "m", [{"role": "user", "content": "hi"}])
    )
    assert text == "whole"


def test_malformed_sse_lines_are_skipped(monkeypatch):
    body = "data: not-json\n\n: a comment\n\n" + _sse(_delta(content="fine"))
    _patch(monkeypatch, _streaming_handler(body))

    _, (text, _) = _drain(
        llm.chat_complete_stream("http://x/v1", "", "m", [{"role": "user", "content": "hi"}])
    )
    assert text == "fine"


# ---- empty-completion diagnosis --------------------------------------------


def test_reasoning_only_completion_names_the_actual_problem(monkeypatch):
    """All budget spent thinking is a distinct failure from a blank reply."""
    body = _sse(_delta(reasoning="thinking and thinking", finish="length"))
    _patch(monkeypatch, _streaming_handler(body))

    with pytest.raises(APIError) as excinfo:
        _drain(
            llm.chat_complete_stream("http://x/v1", "", "m", [{"role": "user", "content": "hi"}])
        )

    assert "thinking" in excinfo.value.message.lower()
    assert excinfo.value.status_code == 502


def test_blocking_path_reports_reasoning_only_the_same_way(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404, json={"detail": "Not Found"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "", "reasoning_content": "still deliberating"},
                        "finish_reason": "length",
                    }
                ]
            },
        )

    _patch(monkeypatch, handler)

    with pytest.raises(APIError) as excinfo:
        llm.chat_complete("http://x/v1", "", "m", [{"role": "user", "content": "hi"}])

    assert "thinking" in excinfo.value.message.lower()


def test_truly_empty_completion_still_reports_empty(monkeypatch):
    _patch(monkeypatch, _streaming_handler(_sse(_delta(content=""))))

    with pytest.raises(APIError) as excinfo:
        _drain(
            llm.chat_complete_stream("http://x/v1", "", "m", [{"role": "user", "content": "hi"}])
        )

    assert "empty" in excinfo.value.message.lower()


# ---- incremental reasoning split (the inline-<think> fallback) --------------


def _split(chunks: list[str]) -> tuple[str, str]:
    from app.agents._common import InlineReasoningSplitter

    splitter = InlineReasoningSplitter()
    answer, reasoning = "", ""
    for chunk in chunks:
        a, r = splitter.push(chunk)
        answer += a
        reasoning += r
    a, r = splitter.flush()
    return answer + a, reasoning + r


def test_split_holds_back_an_unterminated_tag():
    """A '<' that has not closed yet may be any tag — it must not reach the reader."""
    answer, reasoning = _split(["Hello <thi", "nk>plotting</think> world"])
    assert answer == "Hello  world"
    assert reasoning == "plotting"


def test_split_suppresses_harmony_control_tokens():
    answer, _ = _split(["<|chan", "nel|>final<|mess", "age|>The real line."])
    assert "<|" not in answer
    assert answer.endswith("The real line.")


def test_split_passes_clean_prose_through_untouched():
    answer, reasoning = _split(["The night ", "was cold."])
    assert answer == "The night was cold."
    assert reasoning == ""


def test_split_releases_a_bare_less_than_sign_at_the_end():
    """Held-back text is delayed, never dropped."""
    answer, _ = _split(["5 < 6 is true"])
    assert answer == "5 < 6 is true"


# ---- prompt-cache observability --------------------------------------------


def test_usage_out_captures_the_prefix_cache_hit(monkeypatch):
    """Without this figure a cache regression is silent — it just looks like slowness."""
    body = _sse(
        _delta(content="ok"),
        {"choices": [], "usage": {"prompt_tokens": 900, "prompt_tokens_details": {"cached_tokens": 850}}},
    )
    _patch(monkeypatch, _streaming_handler(body))

    usage: dict = {}
    _drain(
        llm.chat_complete_stream(
            "http://x/v1", "", "m", [{"role": "user", "content": "hi"}], usage_out=usage
        )
    )

    assert usage == {"prompt_tokens": 900, "cached_tokens": 850}


def test_usage_out_reports_none_when_the_endpoint_omits_cache_details(monkeypatch):
    """`None` and 0 mean different things: no data vs. nothing reused."""
    _patch(monkeypatch, _streaming_handler(_sse(_delta(content="ok"), _usage(120))))

    usage: dict = {}
    _drain(
        llm.chat_complete_stream(
            "http://x/v1", "", "m", [{"role": "user", "content": "hi"}], usage_out=usage
        )
    )

    assert usage["prompt_tokens"] == 120
    assert usage["cached_tokens"] is None


def test_usage_out_is_filled_on_the_blocking_path_too(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404, json={"detail": "Not Found"})
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 77, "prompt_tokens_details": {"cached_tokens": 70}},
        })

    _patch(monkeypatch, handler)

    usage: dict = {}
    llm.chat_complete_usage(
        "http://x/v1", "", "m", [{"role": "user", "content": "hi"}], usage_out=usage
    )
    assert usage == {"prompt_tokens": 77, "cached_tokens": 70}


def test_usage_out_survives_the_streaming_fallback(monkeypatch):
    """An endpoint that refuses to stream must still report its cache figures."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404, json={"detail": "Not Found"})
        if json.loads(request.content).get("stream"):
            return httpx.Response(400, json={"error": "no streaming"})
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 50, "prompt_tokens_details": {"cached_tokens": 40}},
        })

    _patch(monkeypatch, handler)

    usage: dict = {}
    _drain(
        llm.chat_complete_stream(
            "http://x/v1", "", "m", [{"role": "user", "content": "hi"}], usage_out=usage
        )
    )
    assert usage == {"prompt_tokens": 50, "cached_tokens": 40}


# ---- the reasoning channel has two spellings -------------------------------


def test_vllm_style_reasoning_field_is_read(monkeypatch):
    """vLLM streams `delta.reasoning`; llama.cpp streams `delta.reasoning_content`.

    Reading only one spelling silently discards the whole channel on the other endpoint —
    which looks like "this model does no reasoning" rather than "we never read it", and
    turns a budget spent entirely on thinking into a bare "empty response" error.
    """
    body = _sse(
        {"choices": [{"index": 0, "delta": {"reasoning": "weighing it"}}]},
        {"choices": [{"index": 0, "delta": {"reasoning": " up"}}]},
        _delta(content="I was home."),
    )
    _patch(monkeypatch, _streaming_handler(body))

    deltas, (text, _) = _drain(
        llm.chat_complete_stream("http://x/v1", "", "m", [{"role": "user", "content": "hi"}])
    )

    assert "".join(d.reasoning for d in deltas) == "weighing it up"
    assert text == "I was home."


def test_a_reasoning_only_completion_is_diagnosed_not_called_empty(monkeypatch):
    """The failure mode this spelling bug produced: all budget spent thinking, reported
    as though the model had returned nothing at all."""
    body = _sse(
        {"choices": [{"index": 0, "delta": {"reasoning": "still thinking"},
                      "finish_reason": "length"}]},
    )
    _patch(monkeypatch, _streaming_handler(body))

    with pytest.raises(APIError) as excinfo:
        _drain(
            llm.chat_complete_stream("http://x/v1", "", "m", [{"role": "user", "content": "hi"}])
        )
    assert "thinking" in excinfo.value.message.lower()


def test_blocking_path_reads_the_vllm_spelling_too(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404, json={"detail": "Not Found"})
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "", "reasoning": "deliberating"},
                         "finish_reason": "length"}]
        })

    _patch(monkeypatch, handler)

    with pytest.raises(APIError) as excinfo:
        llm.chat_complete("http://x/v1", "", "m", [{"role": "user", "content": "hi"}])
    assert "thinking" in excinfo.value.message.lower()
