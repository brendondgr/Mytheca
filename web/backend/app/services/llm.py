"""LLM proxy — talk to an OpenAI-compatible endpoint on the backend's behalf.

Listing models and the connection test run **server-side** (not in the browser)
to dodge CORS against local model servers and to keep the API key off the wire to
the client. Errors are mapped to the contract ``APIError`` envelope.

The HTTP client is built by ``get_http_client`` so tests can inject an
``httpx.MockTransport``.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from collections import OrderedDict
from collections.abc import Generator
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from app.core.config import get_settings
from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.schemas.settings import LlmModelsResponse, LlmParams, LlmTestResponse

if TYPE_CHECKING:  # pragma: no cover - typing only
    # Runtime imports of this package stay INSIDE the functions that need it:
    # `llm_providers` imports the adapters, which import this module's siblings,
    # and a module-level import here closes that circle.
    from app.services import llm_providers

logger = logging.getLogger("mytheca.llm")

# Listing models / the connection test are quick; generation (especially slow
# local or reasoning models that think for many tokens) needs a far longer read
# window before we declare the endpoint unreachable.
_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


def _gen_timeout(seconds: float | None = None) -> httpx.Timeout:
    """The generation read window, from ``LLM_GEN_TIMEOUT_SECONDS`` (default 300 s).

    Resolved per call rather than at import so an operator override takes effect without
    a restart. On a streaming call the read window applies *between* chunks, so this
    bounds the silence between tokens rather than the length of the whole generation.

    ``seconds`` overrides it for one call. That matters because the default is sized for
    *prose* — a character writing a paragraph legitimately takes minutes — while the
    structural calls that decide what a turn even does (intent, the beat planner) are
    small JSON judgements that finish in seconds. Sharing one window meant a stalled
    decision cost the player the full prose budget in silence; see
    ``llm_decision_timeout_seconds``.
    """
    window = float(get_settings().llm_gen_timeout_seconds if seconds is None else seconds)
    return httpx.Timeout(window, connect=5.0)


def get_http_client() -> httpx.Client:
    """Return an HTTP client. Patched in tests to use a MockTransport."""
    return httpx.Client(timeout=_TIMEOUT)


def prefix_cache_key(prefix: str) -> str:
    """Short, stable id for a cacheable prompt prefix (prefix-cache observability, §P11).

    vLLM's automatic prefix caching keys on the leading tokens of the prompt; the turn
    loop keeps the World Primer + output contract + stat guidance in a **byte-identical
    system message** across every character in a turn, so those tokens are served from
    the KV cache instead of recomputed per speaker. This id lets the engine log which
    turns share a warm prefix (an empty prefix returns a stable sentinel)."""
    return hashlib.sha256((prefix or "").encode("utf-8")).hexdigest()[:12]


# Last prompt seen per scope (session id), for :func:`shared_prefix_chars`. Bounded so a
# long-lived process cannot accumulate one entry per session forever; the newest scopes are
# the only ones anyone asks about.
_LAST_PROMPT: OrderedDict[str, str] = OrderedDict()
_LAST_PROMPT_MAX = 64


def shared_prefix_chars(scope: str, prompt: str) -> int:
    """How much of ``prompt`` is a byte-identical prefix of the previous one in ``scope``.

    This is the prompt-cache metric we actually control. The server-side counter
    (``usage.prompt_tokens_details.cached_tokens``) is not dependable: vLLM omits the field
    entirely when the hit is zero, which is exactly the case worth catching, so a
    regression would look like missing data rather than a number going down.

    The shared prefix between one call and the next is computed locally, is always
    available, and is the quantity the prompt layout decides. Returns 0 for the first
    prompt in a scope (nothing to compare against).
    """
    previous = _LAST_PROMPT.get(scope)
    _LAST_PROMPT[scope] = prompt
    _LAST_PROMPT.move_to_end(scope)
    while len(_LAST_PROMPT) > _LAST_PROMPT_MAX:
        _LAST_PROMPT.popitem(last=False)
    if previous is None:
        return 0
    limit = min(len(previous), len(prompt))
    i = 0
    while i < limit and previous[i] == prompt[i]:
        i += 1
    return i


def _normalize(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise APIError(400, "bad_request", "A base URL is required (e.g. http://localhost:7070/v1).")
    return base


def _send(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json: dict | None = None,
    timeout: httpx.Timeout | None = None,
) -> httpx.Response:
    client = get_http_client()
    try:
        with client:
            kwargs: dict = {"headers": headers, "json": json}
            if timeout is not None:
                kwargs["timeout"] = timeout
            return client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:  # network/timeout/DNS — never expose internals
        raise APIError(
            502, "bad_gateway", f"Could not reach the model endpoint: {exc.__class__.__name__}."
        ) from exc


# ---- Context-window fitting -------------------------------------------------
# The operator's saved Max tokens is an *output* budget, but an OpenAI-compatible
# server counts prompt + completion against one context window: asking for 48000
# output tokens on a 48000-token model is rejected with a 400 no matter how short
# the prompt, which surfaced as a bare 502 on every generation. We learn the
# window from that 400 (it states the limit), clamp, and retry once; the learned
# limit is cached per endpoint+model so later calls are clamped before sending.
_CONTEXT_LIMIT_RE = re.compile(r"maximum context length is\s+(\d+)\s*tokens", re.IGNORECASE)
_CONTEXT_LIMITS: dict[tuple[str, str], int] = {}
_CHARS_PER_TOKEN = 4  # rough, deliberately conservative prompt estimate
_CONTEXT_RESERVE = 512  # headroom for the chat template / role scaffolding
_MIN_OUTPUT_TOKENS = 256


def _estimate_prompt_tokens(messages: list[dict[str, str]]) -> int:
    chars = sum(len(str(m.get("content") or "")) + len(str(m.get("role") or "")) for m in messages)
    return chars // _CHARS_PER_TOKEN


def _fit_max_tokens(body: dict, limit: int) -> bool:
    """Clamp ``body["max_tokens"]`` so prompt + completion fit ``limit``.

    Returns True when the value changed. Raises when the prompt alone leaves no
    usable room, so the operator sees the real problem instead of a raw upstream 400.
    """
    prompt_tokens = _estimate_prompt_tokens(body.get("messages") or [])
    allowed = limit - prompt_tokens - _CONTEXT_RESERVE
    if allowed < _MIN_OUTPUT_TOKENS:
        raise APIError(
            502,
            "upstream_error",
            f"The prompt is too long for this model's {limit}-token context window. "
            "Use a model with a larger context, or trim the reference material.",
        )
    requested = int(body.get("max_tokens") or 0)
    if requested and requested <= allowed:
        return False
    body["max_tokens"] = allowed
    return True


def _learn_context_limit(key: tuple[str, str], res: httpx.Response) -> int | None:
    """Read the model's context window out of an overflow 400 and cache it."""
    if res.status_code != 400:
        return None
    match = _CONTEXT_LIMIT_RE.search(res.text or "")
    if not match:
        return None
    limit = int(match.group(1))
    _CONTEXT_LIMITS[key] = limit
    logger.info("Learned context window for %s: %d tokens", key[1], limit)
    return limit


def _ensure_ok(res: httpx.Response) -> None:
    if res.is_success:
        return
    detail = res.text[:300]
    raise APIError(
        502,
        "upstream_error",
        f"The model endpoint returned {res.status_code}.",
        {"status": res.status_code, "body": detail},
    )


def stop_is_safe(reasoning: ReasoningEffort | None) -> bool:
    """Whether a ``stop`` sequence may be sent for a call at this reasoning effort.

    **A stop sequence matches the model's REASONING channel, not just its answer.** Measured
    on the deployed llama.cpp route: asked to write ``AAA <END_SCENARIO> BBB`` with
    ``stop: ["<END_SCENARIO>"]``, generation died mid-thought — the reasoning ended at
    ``the token "`` and ``content`` came back **empty**. The same prompt with no ``stop``
    returned ``AAA<END_SCENARIO>BBB`` intact. A model that merely *thinks about* the tag
    kills its own generation before writing a word.

    So a stop sequence is only safe when the thinking channel is off, which on this stack
    means an explicit ``ReasoningEffort.NONE`` — ``None`` sends no budget key at all and the
    server's own default applies (``--reasoning-budget -1`` on the local endpoint: unlimited).

    A tag that has to survive the reasoning channel is parsed out of the finished text
    instead, the way ``<speaker:N>`` already is.

    **This is a property of the engine, not a universal truth**, so the answer comes from
    the active adapter's ``stop_matches_reasoning`` rather than from a constant here.
    Anthropic separates deliberation into its own block and documents ``stop_sequences``
    against the response text; hardcoding llama.cpp's behaviour would drop every stop
    sequence on a provider that has no such problem.
    """
    from app.services import llm_providers

    if not getattr(llm_providers.active_adapter(), "stop_matches_reasoning", True):
        return True
    return reasoning is ReasoningEffort.NONE


def _completion_request(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    params: LlmParams | None,
    *,
    reasoning: ReasoningEffort | None,
    extra_body: dict | None,
    stop: list[str] | None = None,
    stream: bool = False,
) -> tuple[str, dict, tuple[str, str], "llm_providers.ProviderAdapter"]:
    """Build the ``(url, body, limit_key, adapter)`` a chat completion needs.

    Shared by the blocking and streaming paths so they cannot drift on sampler fields,
    the reasoning budget, the learned context-window clamp — or, since the streaming
    path was wired through the seam, on which provider they are talking to.

    ``stream`` reaches BOTH the URL and the body, because the four dialects disagree
    about where it belongs: OpenAI, Anthropic and Ollama say ``"stream": true`` in the
    body, while Gemini selects ``:streamGenerateContent?alt=sse`` in the path. Building
    a streaming body against a non-streaming URL is not an error anywhere — it returns
    one JSON blob and a stream that never types.
    """
    if not model:
        raise APIError(400, "bad_request", "A model is required to generate.")
    from app.services import llm_providers

    p = params or LlmParams()
    adapter = llm_providers.active_adapter()
    url = adapter.chat_url(base_url, model, stream=stream)
    # For the OpenAI-compatible provider this reproduces the body this function
    # used to build literally — key order included, verified by a parity harness
    # against the previous implementation — so the path every existing install
    # runs on is unchanged. Other providers get their own dialect here, which is
    # what makes the stored `provider` field load-bearing rather than decorative.
    body = adapter.build_body(
        llm_providers.ChatRequest(
            model=model,
            messages=messages,
            params=p,
            reasoning=reasoning,
            stop=list(stop) if stop else None,
            stream=stream,
            extra_body=dict(extra_body or {}),
        )
    )
    if reasoning is not None and getattr(adapter, "reasoning_applied_by_caller", False):
        # The OpenAI-compatible family carries the thinking budget under
        # LOCAL-ENGINE keys (`thinking_token_budget` on vLLM,
        # `thinking_budget_tokens` on llama.cpp), and picking between them needs
        # a probe of the endpoint. That is I/O, and adapters are pure — so this
        # one step stays here. Omitting it returns a 200 and simply thinks
        # forever.
        # Local import avoids a circular import (llm_backend imports this module).
        from app.services import llm_backend

        backend = llm_backend.get_backend(base_url, api_key)
        llm_backend.apply_reasoning(body, backend, reasoning)
    limit_key = (_normalize(base_url), model)
    known_limit = _CONTEXT_LIMITS.get(limit_key)
    if known_limit:
        _fit_max_tokens(body, known_limit)
    return url, body, limit_key, adapter


def chat_complete(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    params: LlmParams | None = None,
    *,
    reasoning: ReasoningEffort | None = None,
    extra_body: dict | None = None,
    stop: list[str] | None = None,
    timeout_s: float | None = None,
) -> str:
    """Run one chat completion and return the assistant's (scrubbed) text.

    The general-purpose generation primitive (the authoring agent builds on it).
    Thin wrapper over :func:`chat_complete_usage` that discards the usage figure.
    """
    text, _ = chat_complete_usage(
        base_url, api_key, model, messages, params, reasoning=reasoning,
        extra_body=extra_body, stop=stop, timeout_s=timeout_s,
    )
    return text


def chat_complete_usage(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    params: LlmParams | None = None,
    *,
    reasoning: ReasoningEffort | None = None,
    extra_body: dict | None = None,
    stop: list[str] | None = None,
    usage_out: dict | None = None,
    timeout_s: float | None = None,
) -> tuple[str, int | None]:
    """Run one chat completion; return ``(scrubbed_text, prompt_tokens)``.

    ``usage_out``, when given, is filled with ``prompt_tokens`` and ``cached_tokens``
    (the prefix-cache hit) for this call — see :func:`_record_usage`.

    ``prompt_tokens`` is the server-reported ``usage.prompt_tokens`` — the **exact**
    number of input tokens the model actually saw for this call — or ``None`` when the
    endpoint omits ``usage`` (so the caller can fall back to an estimate). It is the
    honest "context window used" figure the story player's context dial renders.

    Errors map to the contract envelope; an empty/malformed completion is an
    ``upstream_error`` rather than a silent blank.

    When ``reasoning`` is given, the configured inference engine is detected (cached)
    and the matching thinking-token-budget key is added to the request, so reasoning
    models stop thinking once the budget is spent. This is **backend-controlled** —
    callers (the authoring agents) set the effort per operation; it is never exposed
    to the user. On an OpenAI / unknown endpoint the budget is silently omitted.

    ``extra_body`` is merged into the request body — the seam for vLLM guided/structured
    decoding (e.g. ``{"guided_choice": [...]}`` or ``{"guided_json": {...}}``) to pin the
    turn loop's constrained control fields. Ignored by providers that don't support it.
    """
    url, body, limit_key, adapter = _completion_request(
        base_url, api_key, model, messages, params, reasoning=reasoning,
        extra_body=extra_body, stop=stop,
    )
    window = _gen_timeout(timeout_s)
    # `adapter.headers`, not a hardcoded Bearer token. Anthropic authenticates with
    # `x-api-key` plus `anthropic-version` and Gemini with `x-goog-api-key`; sending a
    # Bearer token to either is a 401 that reads exactly like a bad key, so an operator
    # who pasted a perfectly good one spends the afternoon regenerating it.
    headers = adapter.headers(api_key)
    res = _send("POST", url, headers=headers, json=body, timeout=window)
    if not res.is_success:
        limit = _learn_context_limit(limit_key, res)
        if limit and _fit_max_tokens(body, limit):
            res = _send("POST", url, headers=headers, json=body, timeout=window)
    _ensure_ok(res)
    try:
        payload = res.json()
        # `adapter.parse_reply`, not an inlined OpenAI read. This path used to dig out
        # `choices[0].message.content` itself, which meant the seam was wired for the
        # URL and the body and then ignored for the answer: on Anthropic the content is
        # a LIST of typed blocks and on Gemini it is `candidates[0].content.parts`, so
        # both parsed as an empty completion from a perfectly successful call.
        reply = adapter.parse_reply(payload if isinstance(payload, dict) else {})
        content = reply.text.strip()
        raw_reasoning = reply.reasoning
        finish_reason = reply.finish_reason
        prompt_tokens = reply.prompt_tokens
        _record_usage(usage_out, reply)
    except APIError:
        # Gemini raises a typed error for a safety block rather than returning an empty
        # string, which is the more useful answer. Let it through unchanged.
        raise
    except (ValueError, AttributeError, IndexError, KeyError, TypeError) as exc:
        raise APIError(
            502, "upstream_error", "The model endpoint returned an unexpected response."
        ) from exc
    # DIAGNOSTIC (garbled-output investigation): log the EXACT raw completion the server
    # returns, before any scrubbing, using repr() so leaked special/separator tokens and
    # stray glyphs are visible verbatim. At DEBUG so it doesn't flood normal operation —
    # every completion (including successful non-empty ones) passes through here.
    logger.debug("RAW model completion (pre-scrub): %r", content)
    # Reasoning models inline their chain-of-thought + harmony channel tokens
    # (``<|channel|>…``, ``<think>…</think>``) in ``content``; strip them here at the one
    # choke point every agent shares, so the narrator, the character emission parser, and
    # the authoring JSON agents all receive only the model's final answer. The scrub keeps
    # the app's own ``<speaker:>``/``<type:>``/``<thinking>`` markers intact. Local import
    # avoids a circular import (``_common`` imports ``services``).
    from app.agents._common import strip_reasoning

    content = strip_reasoning(content)
    if not content:
        # Reasoning models spend the budget on hidden reasoning tokens and can hit the
        # cap before emitting any visible reply. Surface which of those happened rather
        # than a bare blank. (Shared with the streaming path.)
        _raise_empty_completion(finish_reason, raw_reasoning)
    return content, prompt_tokens


# ---- Streaming generation ---------------------------------------------------
# Endpoints that refused ``stream: true`` (or answered with something that was not an
# event stream). Keyed like the context-limit cache so one refusal does not cost every
# later call a failed attempt.
_NO_STREAM: set[tuple[str, str]] = set()


@dataclass
class StreamDelta:
    """One increment of a streaming completion.

    ``answer`` is prose the caller should show; ``reasoning`` is the model's private
    deliberation. They are separate channels because the model reports them separately —
    modern reasoning endpoints put the latter in ``delta.reasoning_content`` — and
    because showing them differently is the entire point of streaming a turn.
    """

    answer: str = ""
    reasoning: str = ""
    #: Everything already streamed as ``answer`` was actually reasoning — discard it.
    #: Set when a generation closes a thinking block it never opened. Some serving stacks
    #: have the chat template consume the opening ``<think>`` and hand back only the closing
    #: tag, so the deliberation arrives looking exactly like prose until the moment it ends.
    #: Measured live: a narrator beat streamed the model's own checklist ("Never speak for a
    #: character: no dialogue. Good.") into the scene before the tag arrived.
    restart: bool = False


def chat_complete_stream(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    params: LlmParams | None = None,
    *,
    reasoning: ReasoningEffort | None = None,
    extra_body: dict | None = None,
    stop: list[str] | None = None,
    usage_out: dict | None = None,
    timeout_s: float | None = None,
) -> Generator[StreamDelta, None, tuple[str, int | None]]:
    """Stream one chat completion, yielding deltas; return ``(scrubbed_text, prompt_tokens)``.

    ``usage_out``, when given, is filled with ``prompt_tokens`` and ``cached_tokens``
    for this call (the usage frame arrives last, so it is filled near the end).

    The streaming counterpart to :func:`chat_complete_usage`, and the reason a turn can
    show anything before it is finished. Two differences beyond timing:

    * The read timeout applies **between chunks** rather than to the whole response, so a
      long generation no longer trips the generation timeout merely for being long.
    * Reasoning and answer arrive as separate channels — from ``delta.reasoning_content``
      where the endpoint provides it, else split out of ``delta.content`` by
      :class:`~app.agents._common.InlineReasoningSplitter`.

    Falls back to the blocking path (yielding the whole completion as one delta) when the
    endpoint refuses to stream, so a caller never has to care which it got.

    **Provider-dispatched since 2026-08-31.** Every dialect-specific decision — the
    request URL, the auth header, the media type that means "this is a stream", how one
    line becomes an event, and where that event keeps its text, its deliberation, its
    token counts and its finish reason — is asked of the active adapter. Before that,
    this loop read ``data:`` frames and ``choices[0].delta.content`` directly, so
    selecting Anthropic, Gemini or Ollama failed the content-type check, was remembered
    in ``_NO_STREAM``, and degraded every turn to the blocking path: the whole passage
    arriving at once instead of typing out, with no error anywhere.
    """
    stream_key = (_normalize(base_url), model)
    if stream_key in _NO_STREAM:
        return (yield from _blocking_as_stream(
            base_url, api_key, model, messages, params, reasoning=reasoning,
            extra_body=extra_body, stop=stop, usage_out=usage_out, timeout_s=timeout_s,
        ))

    url, body, limit_key, adapter = _completion_request(
        base_url, api_key, model, messages, params, reasoning=reasoning,
        extra_body=extra_body, stop=stop, stream=True,
    )

    from app.agents._common import InlineReasoningSplitter, strip_reasoning

    splitter = InlineReasoningSplitter()
    answer_parts: list[str] = []
    reasoning_parts: list[str] = []
    usage = _StreamUsage()
    finish_reason: str | None = None

    client = get_http_client()
    try:
        with client:
            with client.stream(
                "POST", url, headers=adapter.headers(api_key), json=body,
                timeout=_gen_timeout(timeout_s),
            ) as res:
                if not res.is_success or not _is_stream(adapter, res):
                    res.read()
                    # A 400 naming the context limit is the blocking path's business —
                    # it knows how to clamp and retry. Anything else means "no streaming
                    # here", remembered so the next call goes straight to blocking.
                    if not _learn_context_limit(limit_key, res):
                        _NO_STREAM.add(stream_key)
                    return (yield from _blocking_as_stream(
                        base_url, api_key, model, messages, params,
                        reasoning=reasoning, extra_body=extra_body, usage_out=usage_out,
                        timeout_s=timeout_s,
                    ))
                for line in res.iter_lines():
                    event = adapter.parse_stream_line(line)
                    if event is None:
                        continue
                    # Read everything off the frame BEFORE asking whether it is the last
                    # one. Gemini's terminal frame carries prose and Ollama's carries the
                    # only token counts in the whole stream, so a loop that breaks first
                    # loses a sentence on one provider and the context dial on another.
                    usage.absorb(adapter.stream_usage(event))
                    finish_reason = adapter.stream_finish_reason(event) or finish_reason
                    out = StreamDelta()
                    raw_reasoning = adapter.stream_reasoning(event)
                    if raw_reasoning:
                        out.reasoning += str(raw_reasoning)
                    raw_content = adapter.stream_delta(event)
                    if raw_content:
                        # Kept dialect-neutral on purpose: an inline ``<think>`` block is
                        # a property of the MODEL, not of the wire format, so a llama.cpp
                        # model served through Ollama inlines its reasoning exactly as it
                        # does through an OpenAI-compatible route.
                        answer_text, inline_reasoning = splitter.push(str(raw_content))
                        out.answer += answer_text
                        out.reasoning += inline_reasoning
                        if splitter.took_over():
                            # Everything streamed as prose so far was deliberation. Say so,
                            # and drop it from the accumulated text as well as telling the
                            # consumer — otherwise the finished string still carries it even
                            # though the live view was corrected.
                            out.restart = True
                            reasoning_parts.extend(answer_parts)
                            answer_parts.clear()
                    if out.answer or out.reasoning or out.restart:
                        answer_parts.append(out.answer)
                        reasoning_parts.append(out.reasoning)
                        yield out
                    if adapter.stream_done(event):
                        break
    except httpx.HTTPError as exc:
        raise APIError(
            502, "bad_gateway", f"Could not reach the model endpoint: {exc.__class__.__name__}."
        ) from exc

    _record_usage(usage_out, usage)
    delta_count = len(answer_parts)
    tail_answer, tail_reasoning = splitter.flush()
    if tail_answer or tail_reasoning:
        answer_parts.append(tail_answer)
        reasoning_parts.append(tail_reasoning)
        yield StreamDelta(answer=tail_answer, reasoning=tail_reasoning)

    # The harmony-channel scrub can only run once the whole reply is known (it keeps the
    # text after the LAST channel marker), so it lands here rather than per delta.
    joined = "".join(answer_parts)
    text = strip_reasoning(joined)
    if not text:
        # An empty completion after a seemingly-normal stream is otherwise undiagnosable:
        # the player sees one opaque sentence and the server records nothing. Log what
        # actually arrived — how many deltas, how much raw text, and whether the scrub is
        # what emptied it — so a recurrence can be told apart from a silent upstream.
        logger.warning(
            "Empty completion from %s model=%s: %d delta(s), %d raw answer char(s), "
            "%d reasoning char(s), finish_reason=%r, raw=%r",
            _normalize(base_url), model, delta_count, len(joined),
            len("".join(reasoning_parts)), finish_reason, joined[:400],
        )
        _raise_empty_completion(finish_reason, "".join(reasoning_parts))
    return text, usage.prompt_tokens


def _is_stream(adapter: "llm_providers.ProviderAdapter", res: httpx.Response) -> bool:
    """Whether the response actually is the stream we asked for.

    The media type is the only signal available before reading a byte, and it is
    provider-specific: OpenAI, Anthropic and Gemini answer ``text/event-stream``, Ollama
    answers ``application/x-ndjson``. Insisting on ``event-stream`` for all four rejects
    a perfectly good Ollama stream and falls back to blocking — silently, since a
    fallback is a normal outcome and logs nothing.

    An adapter that declares no media types is trusted; the check exists to catch an
    endpoint answering with a plain JSON error body under a 200, not to police adapters.
    """
    wanted = getattr(adapter, "stream_media_types", ()) or ()
    if not wanted:
        return True
    content_type = res.headers.get("content-type", "")
    return any(kind in content_type for kind in wanted)


@dataclass
class _StreamUsage:
    """The token counts seen so far in a stream, however late they arrive.

    Each dialect reports usage at a different moment — OpenAI in a trailing frame with
    empty ``choices``, Anthropic split across ``message_start`` (input) and the tail
    ``message_delta``, Gemini cumulatively on every frame, Ollama only on the closing
    one. Rather than teach the loop those four rhythms, every frame is offered and the
    last non-``None`` value for each field wins.

    ``None`` is never absorbed over a real figure: Gemini repeats its counts on frames
    that are otherwise empty, and one such frame arriving last would blank a number the
    stream had already reported.
    """

    prompt_tokens: int | None = None
    cached_tokens: int | None = None

    def absorb(self, counts: tuple[int | None, int | None]) -> None:
        prompt, cached = counts
        if prompt is not None:
            self.prompt_tokens = prompt
        if cached is not None:
            self.cached_tokens = cached


def _blocking_as_stream(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    params: LlmParams | None,
    *,
    reasoning: ReasoningEffort | None,
    extra_body: dict | None,
    stop: list[str] | None = None,
    usage_out: dict | None = None,
    timeout_s: float | None = None,
) -> Generator[StreamDelta, None, tuple[str, int | None]]:
    """Run the blocking path and present it as a one-delta stream.

    Lets every caller be written against the streaming shape regardless of what the
    endpoint actually supports — the only visible difference is that the single delta
    arrives at the end instead of the text arriving gradually.
    """
    text, prompt_tokens = chat_complete_usage(
        base_url, api_key, model, messages, params, reasoning=reasoning,
        extra_body=extra_body, stop=stop, usage_out=usage_out, timeout_s=timeout_s,
    )
    yield StreamDelta(answer=text)
    return text, prompt_tokens


def _raise_empty_completion(finish_reason: str | None, reasoning: str) -> None:
    """Raise the most accurate diagnosis available for a completion with no answer."""
    if reasoning.strip():
        # The model produced only private reasoning. Distinct from a blank reply and from
        # a plain length cap: the budget went somewhere, it just never became an answer.
        raise APIError(
            502,
            "upstream_error",
            "The model spent its whole budget thinking and never answered. Lower the "
            "thinking budget or raise Max tokens in Options.",
        )
    if finish_reason == "length":
        raise APIError(
            502,
            "upstream_error",
            "The model hit its token limit before replying. Raise Max tokens in "
            "Options — reasoning models need extra headroom.",
        )
    raise APIError(502, "upstream_error", "The model returned an empty response.")


def _record_usage(sink: dict | None, reply: object) -> None:
    """Fill a caller-supplied dict with this call's token figures, if one was given.

    An out-parameter rather than a widened return type: ``(text, prompt_tokens)`` is
    unpacked in a dozen places and the cache figure is diagnostic, so paying for it with
    an optional kwarg keeps every existing caller untouched.

    Takes anything carrying ``prompt_tokens``/``cached_tokens`` — a
    :class:`~app.services.llm_providers.ChatReply` on the blocking path, a small
    accumulator on the streaming one. It used to take a raw OpenAI payload and read the
    two fields itself, which silently reported ``None`` for every other provider.
    """
    if sink is None:
        return
    sink["prompt_tokens"] = getattr(reply, "prompt_tokens", None)
    sink["cached_tokens"] = getattr(reply, "cached_tokens", None)


def list_models(
    base_url: str, api_key: str, provider: str | None = None
) -> LlmModelsResponse:
    """Ask a provider what it serves. Raises on an unreachable endpoint.

    Prefer `safe_list_models` from any UI path — see the note there.
    """
    from app.services import llm_providers

    adapter = llm_providers.get_adapter(provider)
    if not getattr(adapter, "supports_discovery", True):
        # OpenAI reports no context windows and Anthropic does not list models at
        # all. Where discovery genuinely cannot answer, the answer belongs in
        # config, not in a fabricated request that would 404.
        declared = list(getattr(adapter, "known_models", []) or [])
        return LlmModelsResponse(models=declared, ok=True, source="config" if declared else "none")
    url = adapter.models_url(base_url)
    res = _send("GET", url, headers=adapter.headers(api_key))
    _ensure_ok(res)
    try:
        payload = res.json()
    except ValueError as exc:
        raise APIError(502, "upstream_error", "The model endpoint returned invalid JSON.") from exc
    models = adapter.parse_models(payload if isinstance(payload, dict) else {"data": payload})
    return LlmModelsResponse(models=models, ok=True, source="endpoint")


def safe_list_models(
    base_url: str, api_key: str, provider: str | None = None
) -> LlmModelsResponse:
    """Discovery that never raises into a UI path.

    An unreachable local server is a NORMAL state, not an exception. Letting a
    connection error propagate turns "your GPU box is off" into a 500 that reads
    as "Mytheca is broken", and it takes the Options page down with it — the one
    page an operator visits precisely when an endpoint is misbehaving.

    Returns the three states the picker has to tell apart, on one shape:
      * nothing configured  -> ok=True,  models=[], source="none"
      * unreachable         -> ok=False, models=[], error set
      * reachable, empty    -> ok=True,  models=[], source="endpoint"
    """
    if not (base_url or "").strip():
        return LlmModelsResponse(
            models=[], ok=True, source="none", error="No endpoint configured yet."
        )
    try:
        return list_models(base_url, api_key, provider)
    except APIError as exc:
        # The operator sees the reason; the stack stays in the log.
        logger.info("model discovery failed for %s: %s", base_url, exc.message)
        return LlmModelsResponse(models=[], ok=False, source="none", error=exc.message)
    except Exception as exc:  # noqa: BLE001 - discovery must never take a page down
        logger.exception("unexpected error listing models for %s", base_url)
        return LlmModelsResponse(
            models=[], ok=False, source="none", error=f"{exc.__class__.__name__} while listing models."
        )


def test_chat(
    base_url: str,
    api_key: str,
    model: str,
    params: LlmParams | None,
    provider: str | None = None,
) -> LlmTestResponse:
    """One tiny round trip, in the provider's own dialect.

    This is the check that catches a wrong provider selection, which otherwise
    shows up much later as an empty generation with no error — the silent
    failure mode this whole layer exists to prevent.
    """
    from app.services import llm_providers

    if not model:
        raise APIError(400, "bad_request", "A model is required to run a test.")
    adapter = llm_providers.get_adapter(provider)
    p = params or LlmParams()
    request = llm_providers.ChatRequest(
        model=model,
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        # A test must not cost real output: 16 tokens is enough for "ok".
        params=p.model_copy(update={"max_tokens": min(p.max_tokens, 16)}),
    )
    url = adapter.chat_url(base_url, model)
    body = adapter.build_body(request)
    started = time.perf_counter()
    res = _send("POST", url, headers=adapter.headers(api_key), json=body)
    _ensure_ok(res)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    try:
        reply = adapter.parse_reply(res.json())
        sample = reply.text.strip()
    except (ValueError, AttributeError, IndexError, KeyError):
        sample = ""
    return LlmTestResponse(ok=True, model=model, latency_ms=elapsed_ms, sample=sample[:200])
