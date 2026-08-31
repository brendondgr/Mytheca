"""The provider seam.

These are contract tests, not integration tests: every adapter is PURE, so each
case is a pure function call with no network, no keys and no server. That is the
point of the seam — the four things that differ per provider are exactly the four
things that can be checked offline.

Every assertion here corresponds to a difference that fails SILENTLY in
production if you get it wrong. A wrong auth header 401s loudly; a system prompt
sent as a message role is simply ignored, with a 200.
"""

from __future__ import annotations

import pytest

from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.schemas.settings import LlmParams
from app.services import llm_providers
from app.services.llm_providers import ChatRequest
from app.services.llm_providers.base import split_system

ALL_IDS = ["openai-compatible", "anthropic", "gemini", "ollama"]


def request_for(model: str = "m", **kw) -> ChatRequest:
    return ChatRequest(
        model=model,
        messages=kw.pop(
            "messages",
            [
                {"role": "system", "content": "You are terse."},
                {"role": "user", "content": "hi"},
            ],
        ),
        params=kw.pop("params", LlmParams()),
        **kw,
    )


# ---- registry ---------------------------------------------------------------


def test_registry_exposes_every_adapter():
    assert sorted(p[0] for p in llm_providers.provider_options()) == sorted(ALL_IDS)


@pytest.mark.parametrize("unknown", ["nonsense", "", None, "openai", "local"])
def test_unknown_provider_falls_back_instead_of_raising(unknown):
    """A settings row written by a newer build must not take generation down.

    `openai` and `local` are the two values the pre-adapter row could hold, and
    both meant "the one OpenAI-compatible endpoint".
    """
    assert llm_providers.get_adapter(unknown).id == "openai-compatible"


@pytest.mark.parametrize("pid", ALL_IDS)
def test_every_adapter_implements_the_contract(pid):
    adapter = llm_providers.get_adapter(pid)
    for member in (
        "id",
        "label",
        "stop_matches_reasoning",
        "chat_url",
        "headers",
        "build_body",
        "parse_reply",
        "models_url",
        "parse_models",
        "stream_delta",
        "stream_done",
    ):
        assert hasattr(adapter, member), f"{pid} is missing {member}"


@pytest.mark.parametrize("pid", ALL_IDS)
def test_adapters_do_no_io(pid):
    """An adapter that reaches the network cannot be reasoned about offline."""
    import inspect

    module = inspect.getmodule(type(llm_providers.get_adapter(pid)))
    source = inspect.getsource(module)
    assert "import httpx" not in source
    assert "import requests" not in source


@pytest.mark.parametrize("pid", ALL_IDS)
def test_parse_reply_never_raises_a_bare_parser_error(pid):
    """A junk payload must produce a reply or a TYPED error — never an IndexError.

    The contract is not "cannot fail"; it is "cannot fail incomprehensibly".
    Gemini returns HTTP 200 with NO candidates for a blocked prompt, and the
    naive `candidates[0]` read is an IndexError that reaches the operator as a
    bug in Mytheca rather than as a safety block. An `APIError` naming the block
    reason is the correct outcome there, so it is allowed here.
    """
    adapter = llm_providers.get_adapter(pid)
    for payload in ({}, {"choices": []}, {"candidates": []}, {"content": []}):
        try:
            reply = adapter.parse_reply(payload)
        except APIError:
            continue  # typed, explained, and surfaced to the caller
        assert isinstance(reply.text, str)


# ---- auth and routing -------------------------------------------------------


def test_anthropic_uses_x_api_key_not_bearer():
    """Bearer is an OpenAI habit; Anthropic rejects it."""
    headers = llm_providers.get_adapter("anthropic").headers("sk-test")
    assert headers["x-api-key"] == "sk-test"
    assert "anthropic-version" in headers
    assert "Authorization" not in headers


def test_gemini_puts_the_key_in_a_header_never_the_url():
    """A key in a query string leaks into logs, history and referrers."""
    adapter = llm_providers.get_adapter("gemini")
    assert adapter.headers("k")["x-goog-api-key"] == "k"
    url = adapter.chat_url("https://generativelanguage.googleapis.com", "gemini-2.5-pro")
    assert "k" not in url.split("?")[-1] or "?" not in url
    assert "gemini-2.5-pro" in url  # the model rides in the PATH
    assert ":generateContent" in url


def test_openai_compatible_keeps_bearer_and_the_v1_shape():
    adapter = llm_providers.get_adapter("openai-compatible")
    assert adapter.headers("k")["Authorization"] == "Bearer k"
    assert adapter.chat_url("http://x/v1", "m") == "http://x/v1/chat/completions"
    assert adapter.models_url("http://x/v1") == "http://x/v1/models"


def test_openai_compatible_sends_no_auth_header_without_a_key():
    """Local servers commonly reject an empty Bearer outright."""
    assert "Authorization" not in llm_providers.get_adapter("openai-compatible").headers("")


def test_ollama_uses_its_native_endpoints():
    adapter = llm_providers.get_adapter("ollama")
    assert adapter.chat_url("http://localhost:11434", "llama3").endswith("/api/chat")
    assert adapter.models_url("http://localhost:11434").endswith("/api/tags")


# ---- body shaping -----------------------------------------------------------


def test_split_system_hoists_every_system_message():
    system, rest = split_system(
        [
            {"role": "system", "content": "a"},
            {"role": "user", "content": "u"},
            {"role": "system", "content": "b"},
        ]
    )
    assert system == "a\n\nb"
    assert [m["role"] for m in rest] == ["user"]


def test_anthropic_hoists_system_and_requires_max_tokens():
    """A system role left in `messages` is ignored — with a 200 and no error."""
    body = llm_providers.get_adapter("anthropic").build_body(request_for())
    assert body["system"]
    assert all(m["role"] != "system" for m in body["messages"])
    assert isinstance(body.get("max_tokens"), int) and body["max_tokens"] > 0


def test_anthropic_omits_the_penalties_it_has_no_concept_of():
    body = llm_providers.get_adapter("anthropic").build_body(request_for())
    assert "frequency_penalty" not in body
    assert "presence_penalty" not in body


def test_gemini_renames_the_whole_envelope():
    body = llm_providers.get_adapter("gemini").build_body(request_for())
    assert "contents" in body and "messages" not in body
    assert "generationConfig" in body
    # The sampler fields are renamed, not merely re-cased.
    assert "maxOutputTokens" in body["generationConfig"]


def test_ollama_must_disable_streaming_explicitly():
    """/api/chat streams by DEFAULT; a blocking caller that forgets gets NDJSON."""
    body = llm_providers.get_adapter("ollama").build_body(request_for())
    assert body["stream"] is False
    assert "options" in body


def test_openai_compatible_keeps_todays_body_exactly():
    """This path is what every existing install already runs on."""
    body = llm_providers.get_adapter("openai-compatible").build_body(
        request_for(params=LlmParams(temperature=0.3, max_tokens=99, top_p=0.9))
    )
    assert body["model"] == "m"
    assert body["temperature"] == 0.3
    assert body["max_tokens"] == 99
    assert body["top_p"] == 0.9
    assert "frequency_penalty" in body and "presence_penalty" in body
    # The system message stays a message here — OpenAI's shape keeps it inline.
    assert body["messages"][0]["role"] == "system"


def test_stop_sequences_are_a_provider_property_not_a_constant():
    """Measured on llama.cpp: a stop sequence matches the REASONING channel too,
    killing a generation mid-thought and returning empty content. That is an
    engine behaviour, so it must not be applied to providers where it is false.
    """
    assert llm_providers.get_adapter("openai-compatible").stop_matches_reasoning is True
    assert llm_providers.get_adapter("anthropic").stop_matches_reasoning is False
    assert llm_providers.get_adapter("gemini").stop_matches_reasoning is False


# ---- reply parsing ----------------------------------------------------------


def test_openai_compatible_reads_both_reasoning_spellings():
    """vLLM says `reasoning`; llama.cpp says `reasoning_content`. Both are live."""
    adapter = llm_providers.get_adapter("openai-compatible")
    for key in ("reasoning", "reasoning_content"):
        reply = adapter.parse_reply(
            {"choices": [{"message": {"content": "hi", key: "thought"}}]}
        )
        assert reply.text == "hi"
        assert reply.reasoning == "thought"


def test_openai_compatible_reads_usage_and_cache():
    reply = llm_providers.get_adapter("openai-compatible").parse_reply(
        {
            "choices": [{"message": {"content": "x"}}],
            "usage": {"prompt_tokens": 12, "prompt_tokens_details": {"cached_tokens": 4}},
        }
    )
    assert reply.prompt_tokens == 12
    assert reply.cached_tokens == 4


def test_anthropic_reads_typed_blocks_and_its_own_usage_names():
    """Anthropic says input_tokens, not prompt_tokens. Read the wrong one and the
    player-facing context dial goes blank with no error anywhere."""
    reply = llm_providers.get_adapter("anthropic").parse_reply(
        {
            "content": [
                {"type": "thinking", "thinking": "hmm"},
                {"type": "text", "text": "hello"},
            ],
            "usage": {"input_tokens": 20, "cache_read_input_tokens": 5},
        }
    )
    assert reply.text == "hello"
    assert reply.reasoning == "hmm"
    # 20 + 5, NOT 20. Anthropic's cache counts are ADDITIVE — the total the model
    # actually saw is input_tokens + cache_read + cache_creation — whereas
    # OpenAI's `cached_tokens` is a subset already inside `prompt_tokens`.
    # Passing input_tokens straight through under-reports by the whole cached
    # prefix, and under-reports MORE as the scene grows and caching does more
    # work: the context dial falls while the real context climbs.
    assert reply.prompt_tokens == 25
    assert reply.cached_tokens == 5


def test_gemini_blocked_prompt_is_reported_as_a_block_not_a_parse_failure():
    """HTTP 200, zero candidates. The single most important Gemini behaviour.

    An empty string would be indistinguishable from "the model had nothing to
    say", which is the wrong thing to tell an author whose prompt was refused.
    """
    with pytest.raises(APIError) as excinfo:
        llm_providers.get_adapter("gemini").parse_reply(
            {"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}}
        )
    assert "SAFETY" in str(excinfo.value)


# ---- discovery --------------------------------------------------------------


def test_each_provider_parses_its_own_listing_shape():
    """Three shapes, three field names. Get it wrong and the picker is empty for
    a perfectly healthy endpoint."""
    assert llm_providers.get_adapter("openai-compatible").parse_models(
        {"data": [{"id": "a"}, {"id": "b"}]}
    ) == ["a", "b"]
    assert llm_providers.get_adapter("ollama").parse_models(
        {"models": [{"name": "llama3:8b"}]}
    ) == ["llama3:8b"]
    gemini = llm_providers.get_adapter("gemini").parse_models(
        {"models": [{"name": "models/gemini-2.5-pro"}]}
    )
    # The "models/" prefix is Google's, not part of the id an operator picks.
    assert gemini == ["gemini-2.5-pro"]


@pytest.mark.parametrize("pid", ALL_IDS)
def test_parse_models_survives_junk(pid):
    adapter = llm_providers.get_adapter(pid)
    for payload in ({}, {"data": None}, {"models": None}, {"data": ["a"]}):
        assert isinstance(adapter.parse_models(payload), list)


# ---- streaming --------------------------------------------------------------


def test_openai_compatible_stream_delta_and_done():
    adapter = llm_providers.get_adapter("openai-compatible")
    assert adapter.stream_delta({"choices": [{"delta": {"content": "ab"}}]}) == "ab"
    assert adapter.stream_delta({"choices": [{"delta": {}}]}) == ""


def test_anthropic_streams_typed_events_not_openai_deltas():
    adapter = llm_providers.get_adapter("anthropic")
    delta = adapter.stream_delta(
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "ab"}}
    )
    assert delta == "ab"
    # An OpenAI-shaped chunk carries nothing here, and must not throw.
    assert adapter.stream_delta({"choices": [{"delta": {"content": "x"}}]}) == ""
    assert adapter.stream_done({"type": "message_stop"}) is True


@pytest.mark.parametrize("pid", ALL_IDS)
def test_stream_helpers_survive_junk(pid):
    adapter = llm_providers.get_adapter(pid)
    for event in ({}, {"choices": []}, {"delta": None}):
        assert isinstance(adapter.stream_delta(event), str)
        assert isinstance(adapter.stream_done(event), bool)


# ---- reasoning --------------------------------------------------------------


def test_reasoning_effort_reaches_each_provider_in_its_own_dialect():
    """The budget is one number; every provider spells its carrier differently.
    An unrecognised top-level key is a 400 on the hosted providers."""
    high = ReasoningEffort.HIGH
    anthropic_body = llm_providers.get_adapter("anthropic").build_body(
        request_for(reasoning=high)
    )
    assert "thinking" in anthropic_body
    gemini_body = llm_providers.get_adapter("gemini").build_body(request_for(reasoning=high))
    assert "thinkingConfig" in gemini_body.get("generationConfig", {})
