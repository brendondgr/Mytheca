"""LLM proxy — talk to an OpenAI-compatible endpoint on the backend's behalf.

Listing models and the connection test run **server-side** (not in the browser)
to dodge CORS against local model servers and to keep the API key off the wire to
the client. Errors are mapped to the contract ``APIError`` envelope.

The HTTP client is built by ``get_http_client`` so tests can inject an
``httpx.MockTransport``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections import OrderedDict
from collections.abc import Generator
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.schemas.settings import LlmModelsResponse, LlmParams, LlmTestResponse

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


def _headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


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
    """
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
) -> tuple[str, dict, tuple[str, str]]:
    """Build the ``(url, body, limit_key)`` a chat completion needs.

    Shared by the blocking and streaming paths so they cannot drift on sampler fields,
    the reasoning budget, or the learned context-window clamp.
    """
    if not model:
        raise APIError(400, "bad_request", "A model is required to generate.")
    p = params or LlmParams()
    url = f"{_normalize(base_url)}/chat/completions"
    body: dict = {
        "model": model,
        "messages": messages,
        "temperature": p.temperature,
        "max_tokens": p.max_tokens,
        "top_p": p.top_p,
        "frequency_penalty": p.frequency_penalty,
        "presence_penalty": p.presence_penalty,
    }
    if extra_body:
        body.update(extra_body)
    # Dropped rather than raised when the channel is on: a caller asking for a stop sequence
    # wants a bounded generation, and refusing the whole call would be a worse answer than
    # generating without it. The reason is logged so it is not invisible.
    if stop:
        if stop_is_safe(reasoning):
            body["stop"] = list(stop)
        else:
            logger.debug("stop sequence dropped: reasoning channel is on (%s)", reasoning)
    if reasoning is not None:
        # Local import avoids a circular import (llm_backend imports this module).
        from app.services import llm_backend

        backend = llm_backend.get_backend(base_url, api_key)
        llm_backend.apply_reasoning(body, backend, reasoning)
    limit_key = (_normalize(base_url), model)
    known_limit = _CONTEXT_LIMITS.get(limit_key)
    if known_limit:
        _fit_max_tokens(body, known_limit)
    return url, body, limit_key


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
    url, body, limit_key = _completion_request(
        base_url, api_key, model, messages, params, reasoning=reasoning,
        extra_body=extra_body, stop=stop,
    )
    window = _gen_timeout(timeout_s)
    res = _send("POST", url, headers=_headers(api_key), json=body, timeout=window)
    if not res.is_success:
        limit = _learn_context_limit(limit_key, res)
        if limit and _fit_max_tokens(body, limit):
            res = _send("POST", url, headers=_headers(api_key), json=body, timeout=window)
    _ensure_ok(res)
    try:
        payload = res.json()
        choices = payload.get("choices") or []
        choice = choices[0] if choices else {}
        message = choice.get("message", {}) or {}
        content = (message.get("content") or "").strip()
        # Reasoning endpoints report their deliberation in its own field. Reading it
        # here is what lets an empty answer be diagnosed as "spent the budget thinking"
        # rather than a bare blank reply.
        raw_reasoning = _reasoning_field(message)
        finish_reason = choice.get("finish_reason")
        prompt_tokens = _prompt_tokens(payload)
        _record_usage(usage_out, payload)
    except (ValueError, AttributeError, IndexError, TypeError) as exc:
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
    """
    stream_key = (_normalize(base_url), model)
    if stream_key in _NO_STREAM:
        return (yield from _blocking_as_stream(
            base_url, api_key, model, messages, params, reasoning=reasoning,
            extra_body=extra_body, stop=stop, usage_out=usage_out, timeout_s=timeout_s,
        ))

    url, body, limit_key = _completion_request(
        base_url, api_key, model, messages, params, reasoning=reasoning,
        extra_body=extra_body, stop=stop,
    )
    body["stream"] = True
    body["stream_options"] = {"include_usage": True}

    from app.agents._common import InlineReasoningSplitter, strip_reasoning

    splitter = InlineReasoningSplitter()
    answer_parts: list[str] = []
    reasoning_parts: list[str] = []
    prompt_tokens: int | None = None
    finish_reason: str | None = None

    client = get_http_client()
    try:
        with client:
            with client.stream(
                "POST", url, headers=_headers(api_key), json=body,
                timeout=_gen_timeout(timeout_s),
            ) as res:
                if not res.is_success or "event-stream" not in res.headers.get("content-type", ""):
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
                    chunk = _sse_payload(line)
                    if chunk is None:
                        continue
                    if chunk is _SSE_DONE:
                        break
                    usage_tokens = _prompt_tokens(chunk)
                    if usage_tokens is not None:
                        prompt_tokens = usage_tokens
                        _record_usage(usage_out, chunk)
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0] or {}
                    finish_reason = choice.get("finish_reason") or finish_reason
                    delta = choice.get("delta") or {}
                    out = StreamDelta()
                    raw_reasoning = _reasoning_field(delta)
                    if raw_reasoning:
                        out.reasoning += str(raw_reasoning)
                    raw_content = delta.get("content") or ""
                    if raw_content:
                        answer_text, inline_reasoning = splitter.push(str(raw_content))
                        out.answer += answer_text
                        out.reasoning += inline_reasoning
                    if out.answer or out.reasoning:
                        answer_parts.append(out.answer)
                        reasoning_parts.append(out.reasoning)
                        yield out
    except httpx.HTTPError as exc:
        raise APIError(
            502, "bad_gateway", f"Could not reach the model endpoint: {exc.__class__.__name__}."
        ) from exc

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
    return text, prompt_tokens


#: Sentinel for the SSE terminator, distinct from "this line carried no payload".
_SSE_DONE: dict = {}


def _sse_payload(line: str) -> dict | None:
    """Parse one SSE line into its JSON payload, ``_SSE_DONE``, or ``None`` to skip."""
    line = (line or "").strip()
    if not line or not line.startswith("data:"):
        return None
    data = line[len("data:") :].strip()
    if data == "[DONE]":
        return _SSE_DONE
    try:
        parsed = json.loads(data)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


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


#: Field names carrying a model's deliberation, in the order they are checked.
#:
#: There is no standard here, and the difference is not cosmetic: reading only one spelling
#: silently discards the whole channel on any endpoint that uses the other, which then
#: looks like "this model does no reasoning" rather than "we did not read it".
#:  * ``reasoning_content`` — llama.cpp.
#:  * ``reasoning``         — vLLM (observed on qwen38-27B-awq behind the relay).
_REASONING_FIELDS = ("reasoning_content", "reasoning")


def _reasoning_field(payload: dict) -> str:
    """The deliberation text from a delta or message, whichever spelling it uses."""
    if not isinstance(payload, dict):
        return ""
    for name in _REASONING_FIELDS:
        value = payload.get(name)
        if value:
            return str(value)
    return ""


def _cached_tokens(payload: dict) -> int | None:
    """Extract ``usage.prompt_tokens_details.cached_tokens`` — the prefix-cache hit.

    How many of this call's prompt tokens the server served from its KV cache instead of
    re-processing. It is the only honest measure of whether the prompt is laid out so a
    conversation's history can be reused between turns, and without it a cache regression
    is completely silent: latency simply creeps up as the scene gets longer.

    ``None`` when the endpoint reports no ``prompt_tokens_details`` (many do not).
    """
    usage = payload.get("usage") if isinstance(payload, dict) else None
    details = usage.get("prompt_tokens_details") if isinstance(usage, dict) else None
    value = details.get("cached_tokens") if isinstance(details, dict) else None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _record_usage(sink: dict | None, payload: dict) -> None:
    """Fill a caller-supplied dict with this call's token figures, if one was given.

    An out-parameter rather than a widened return type: ``(text, prompt_tokens)`` is
    unpacked in a dozen places and the cache figure is diagnostic, so paying for it with
    an optional kwarg keeps every existing caller untouched.
    """
    if sink is None:
        return
    sink["prompt_tokens"] = _prompt_tokens(payload)
    sink["cached_tokens"] = _cached_tokens(payload)


def _prompt_tokens(payload: dict) -> int | None:
    """Extract ``usage.prompt_tokens`` from an OpenAI-compatible completion payload.

    Returns ``None`` when the endpoint omits ``usage`` or the value is not a positive
    integer, so callers degrade to an estimate instead of surfacing a bogus zero.
    """
    usage = payload.get("usage") if isinstance(payload, dict) else None
    value = usage.get("prompt_tokens") if isinstance(usage, dict) else None
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def list_models(base_url: str, api_key: str) -> LlmModelsResponse:
    url = f"{_normalize(base_url)}/models"
    res = _send("GET", url, headers=_headers(api_key))
    _ensure_ok(res)
    try:
        payload = res.json()
    except ValueError as exc:
        raise APIError(502, "upstream_error", "The model endpoint returned invalid JSON.") from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    items = data if isinstance(data, list) else (payload if isinstance(payload, list) else [])
    models = [
        str(m.get("id")) if isinstance(m, dict) else str(m)
        for m in items
        if (isinstance(m, dict) and m.get("id")) or isinstance(m, str)
    ]
    return LlmModelsResponse(models=models)


def test_chat(base_url: str, api_key: str, model: str, params: LlmParams | None) -> LlmTestResponse:
    if not model:
        raise APIError(400, "bad_request", "A model is required to run a test.")
    p = params or LlmParams()
    url = f"{_normalize(base_url)}/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
        "temperature": p.temperature,
        "max_tokens": min(p.max_tokens, 16),
    }
    started = time.perf_counter()
    res = _send("POST", url, headers=_headers(api_key), json=body)
    _ensure_ok(res)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    try:
        payload = res.json()
        choices = payload.get("choices") or []
        sample = (choices[0].get("message", {}).get("content") or "").strip() if choices else ""
    except (ValueError, AttributeError, IndexError):
        sample = ""
    return LlmTestResponse(ok=True, model=model, latency_ms=elapsed_ms, sample=sample[:200])
