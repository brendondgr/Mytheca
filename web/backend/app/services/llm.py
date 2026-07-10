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
import time

import httpx

from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.schemas.settings import LlmModelsResponse, LlmParams, LlmTestResponse

logger = logging.getLogger("velora.llm")

# Listing models / the connection test are quick; generation (especially slow
# local or reasoning models that think for many tokens) needs a far longer read
# window before we declare the endpoint unreachable.
_TIMEOUT = httpx.Timeout(20.0, connect=5.0)
_GEN_TIMEOUT = httpx.Timeout(300.0, connect=5.0)


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


def chat_complete(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    params: LlmParams | None = None,
    *,
    reasoning: ReasoningEffort | None = None,
    extra_body: dict | None = None,
) -> str:
    """Run one chat completion and return the assistant's (scrubbed) text.

    The general-purpose generation primitive (the authoring agent builds on it).
    Thin wrapper over :func:`chat_complete_usage` that discards the usage figure.
    """
    text, _ = chat_complete_usage(
        base_url, api_key, model, messages, params, reasoning=reasoning, extra_body=extra_body
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
) -> tuple[str, int | None]:
    """Run one chat completion; return ``(scrubbed_text, prompt_tokens)``.

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
    if not model:
        raise APIError(400, "bad_request", "A model is required to generate.")
    p = params or LlmParams()
    url = f"{_normalize(base_url)}/chat/completions"
    body = {
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
    if reasoning is not None:
        # Local import avoids a circular import (llm_backend imports this module).
        from app.services import llm_backend

        backend = llm_backend.get_backend(base_url, api_key)
        llm_backend.apply_reasoning(body, backend, reasoning)
    res = _send("POST", url, headers=_headers(api_key), json=body, timeout=_GEN_TIMEOUT)
    _ensure_ok(res)
    try:
        payload = res.json()
        choices = payload.get("choices") or []
        choice = choices[0] if choices else {}
        content = (choice.get("message", {}).get("content") or "").strip()
        finish_reason = choice.get("finish_reason")
        prompt_tokens = _prompt_tokens(payload)
    except (ValueError, AttributeError, IndexError, TypeError) as exc:
        raise APIError(
            502, "upstream_error", "The model endpoint returned an unexpected response."
        ) from exc
    # TEMP DIAGNOSTIC (garbled-output investigation): log the EXACT raw completion the
    # server returns, before any scrubbing, using repr() so leaked special/separator
    # tokens and stray glyphs are visible verbatim. Remove once the cause is confirmed.
    logger.warning("RAW model completion (pre-scrub): %r", content)
    # Reasoning models inline their chain-of-thought + harmony channel tokens
    # (``<|channel|>…``, ``<think>…</think>``) in ``content``; strip them here at the one
    # choke point every agent shares, so the narrator, the character emission parser, and
    # the authoring JSON agents all receive only the model's final answer. The scrub keeps
    # the app's own ``<speaker:>``/``<type:>``/``<thinking>`` markers intact. Local import
    # avoids a circular import (``_common`` imports ``services``).
    from app.agents._common import strip_reasoning

    content = strip_reasoning(content)
    if not content:
        # Reasoning models spend the budget on hidden reasoning tokens and can hit
        # the cap before emitting any visible reply (finish_reason == "length").
        # Surface that as something the operator can act on rather than a bare blank.
        if finish_reason == "length":
            raise APIError(
                502,
                "upstream_error",
                "The model hit its token limit before replying. Raise Max tokens in "
                "Options — reasoning models need extra headroom.",
            )
        raise APIError(502, "upstream_error", "The model returned an empty response.")
    return content, prompt_tokens


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
