"""Ollama, spoken natively.

Ollama also serves an OpenAI-compatible surface at ``/v1``, and an operator who
wants it does **not** need this file: they pick the ``openai-compatible``
provider and give it a base URL ending in ``/v1``. This adapter exists because
that layer discards most of what the product asks for — ``num_ctx`` cannot be
set through it at all, ``think`` is not accepted, and the model listing is
reduced to bare ids with no capabilities, size or context length. The native
``/api`` surface reports all of it, so that is what is implemented here.

Three things this adapter cannot do for the caller, being pure:

**Timeouts must be two numbers, not one.** A model that is not resident pays its
full load time on the next request — a cold 30B on a slow disk is minutes before
the first token, while every call after it answers immediately (``keep_alive``
defaults to five minutes, then the weights are evicted again). A single timeout
sized for that cold start also means a server that is simply *not running* hangs
for the same duration. Set a short **connect** timeout so a dead port fails fast
and a long **read** timeout so a slow generation is tolerated. Passing
``keep_alive`` in ``extra_body`` is how a caller buys a longer residency; it is
not set here because eviction is the operator's memory policy, not ours.

**The stream is newline-delimited JSON**, ``Content-Type:
application/x-ndjson``. There are no ``data:`` prefixes and no ``[DONE]``
sentinel. A reader that gates on ``text/event-stream`` before believing a
response is streamed will classify a perfectly healthy Ollama as "this endpoint
refuses to stream" and fall back to blocking forever after.

**The context window has to be handed in, or the prompt is cut without a word.**
Ollama does not size ``num_ctx`` from the prompt it was given. Anything past the
window is dropped before generation — no error, no warning, no field in the reply
admitting it; the scene just loses its oldest context and the model answers as if
it never existed. The server default is VRAM-tiered (<24 GiB → 4 K, 24–48 GiB →
32 K, ≥48 GiB → 256 K), so on an ordinary desktop it is **4 K** while Mytheca's
``max_context_tokens`` defaults to **16384** — `context_budget` packs a prompt to
four times the window it will actually be read in, every turn, silently. Give the
adapter the configured number (``OllamaAdapter(context_window=…)``, or the same
attribute on the shared instance) and it rides on every request as
``options.num_ctx``; a caller can also pass ``extra_body={"options":
{"num_ctx": N}}`` per call, which wins over both. Left unset, nothing is sent and
the server's own default stands — the honest failure, not a guess that costs the
operator VRAM they may not have. The authoritative per-model figure is under an
architecture-prefixed key in ``POST /api/show``, which this pure adapter cannot
call.
"""

from __future__ import annotations

import json
import logging
from typing import Final

from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.schemas.settings import LlmParams
from app.services.llm_providers.base import ChatReply, ChatRequest, normalize_base

# Deliberately the same logger name ``services/llm.py`` and the OpenAI-compatible
# adapter use: an operator debugging generation filters on one name, and a
# provider-specific logger would drop out of that filter exactly when they are
# hunting a provider-specific problem.
logger = logging.getLogger("mytheca.llm")

#: What ``/api/chat`` sets on a streaming response. Exported so a caller checking
#: the header before consuming the body checks for the right one.
STREAM_CONTENT_TYPE: Final = "application/x-ndjson"

#: :class:`ReasoningEffort` → Ollama's ``think`` level.
#:
#: There is no token budget here. ``THINKING_BUDGET``'s numbers (128 … 4096) have
#: no counterpart on this API — ``think`` takes a level, one of
#: ``low`` / ``medium`` / ``high`` / ``max`` (or a bare bool) — so the six-rung
#: ladder compresses onto four and the exact budget a call site chose is lost.
#: That is a real capability difference, not an oversight: an Ollama model cannot
#: be told to stop thinking after 512 tokens.
#:
#: The pairs that merge are the adjacent ones (QUICK+LOW, HIGH+VERY_HIGH); MAX
#: keeps a rung of its own because Ollama has a fourth level. This map read
#: ``"high"`` for both VERY_HIGH and MAX until 2026-08-31 — a three-level collapse
#: that is correct for Gemini, whose ladder genuinely stops at ``high``, and wrong
#: here: the top rung of the product's ladder was quietly capped at Ollama's third.
_THINK_LEVELS: Final[dict[ReasoningEffort, str]] = {
    ReasoningEffort.QUICK: "low",
    ReasoningEffort.LOW: "low",
    ReasoningEffort.MEDIUM: "medium",
    ReasoningEffort.HIGH: "high",
    ReasoningEffort.VERY_HIGH: "high",
    ReasoningEffort.MAX: "max",
}


def _positive_int(value: object) -> int | None:
    """An int that is genuinely a count, else ``None``.

    Mirrors ``llm._prompt_tokens``: a zero or missing figure degrades to "unknown"
    so the caller estimates, rather than reporting a confident zero into the
    player-facing context dial.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _error_text(payload: object) -> str:
    """The message from an Ollama failure frame, or ``""`` when it is not one.

    ``/api/chat`` reports a failure as a bare ``{"error": "..."}`` object, and it
    is the *same* object either way: it can be the whole blocking body, or one
    NDJSON line arriving mid-stream after a 200 and after real content. One reader
    for both is the point. The two paths used to disagree — blocking raised, while
    the streaming side saw an object with no ``message`` and no ``done``, returned
    ``""`` from ``stream_delta`` and ``False`` from ``stream_done``, and left the
    consumer holding a stream that had already failed: no text, no termination, no
    reason, until something else timed out.

    A frame that carries a ``message`` is a normal frame and is never treated as
    an error, which is the condition the blocking path has always used.
    """
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if not error or payload.get("message"):
        return ""
    return str(error)


def _format_from_extra(extra: dict) -> dict | str | None:
    """Pull constrained decoding out of ``extra_body`` and restate it Ollama's way.

    Call sites ask for a schema in OpenAI's vocabulary (``response_format``) or
    vLLM's (``guided_json``). Ollama's is a top-level ``format`` holding the bare
    schema, or the string ``"json"``. Forwarding the original key untouched is the
    worst available outcome: it is simply unknown here, so the request succeeds,
    decoding is unconstrained, and the failure surfaces much later as "the model
    wrote prose where JSON was expected" with nothing pointing at the provider.

    Mutates ``extra`` — the recognised keys are consumed so they are not also
    merged into the body as dead weight.
    """
    guided = extra.pop("guided_json", None)
    response_format = extra.pop("response_format", None)
    if isinstance(guided, dict):
        return guided
    if isinstance(response_format, dict):
        nested = response_format.get("json_schema")
        schema = nested.get("schema") if isinstance(nested, dict) else None
        if isinstance(schema, dict):
            return schema
        if response_format.get("type") == "json_object":
            return "json"
    return None


class OllamaAdapter:
    """Ollama's native ``/api`` dialect."""

    id: str = "ollama"
    label: str = "Ollama (local)"

    #: Not measured on Ollama, and deliberately not assumed. The llama.cpp finding
    #: that a ``stop`` sequence also matches the reasoning channel is a property of
    #: that server's sampler; Ollama's runner descends from llama.cpp, so the same
    #: interaction is *plausible* — but it splits thinking into its own ``thinking``
    #: field rather than inlining it, and the reference says nothing either way.
    #: Guessing ``True`` would silently drop every caller's stop sequence on a hunch.
    #: If a generation here ever comes back empty with a non-empty ``thinking``,
    #: this is the flag to flip, and it belongs flipped with a measurement beside it.
    stop_matches_reasoning: bool = False

    #: Prefilled when an operator switches to this provider and has no URL yet.
    #: A blank field beside a provider that only ever has one endpoint is a
    #: question with one right answer, asked for no reason.
    default_base_url: str = "http://localhost:11434"

    #: The context window to ask for, in tokens, or ``None`` to leave the server's
    #: own (VRAM-tiered) default alone. See the module docstring: this is the one
    #: knob standing between a 16 K prompt and a 4 K window, and getting it wrong
    #: costs the oldest half of the scene with nothing logged anywhere.
    #:
    #: The number to put here is the ``llm`` settings row's ``max_context_tokens``
    #: — the same figure ``context_budget`` packs the prompt against, because the
    #: bug is precisely the two disagreeing. It defaults to ``None`` rather than to
    #: that value because this adapter cannot read settings without doing I/O, and
    #: because a window guessed high costs the operator VRAM they may not have.
    context_window: int | None = None

    def __init__(self, context_window: int | None = None) -> None:
        """Config, not per-call state — the adapter stays stateless between calls.

        The seam builds one adapter per provider and reuses it, so this is set
        once from the settings row (at construction, or by assigning the attribute
        on the shared instance, the way ``llm_providers._ACTIVE`` is kept in sync).
        A caller needing a different window for one request passes
        ``extra_body={"options": {"num_ctx": N}}``, which is merged after this and
        therefore wins.
        """
        if context_window is not None:
            self.context_window = context_window

    # ---- addressing --------------------------------------------------------

    def _root(self, base_url: str) -> str:
        """The server root, with an OpenAI-shaped suffix removed.

        Every other provider in this seam wants a base URL ending in ``/v1``, and
        an operator configuring their fourth endpoint types it out of habit. Left
        in place it produces ``…/v1/api/chat`` — a 404 that reads as a broken
        server rather than a wrong URL. ``/api`` is trimmed for the same reason,
        since the docs quote the endpoints with that prefix already attached.
        """
        base = normalize_base(base_url)
        for suffix in ("/v1", "/api"):
            if base.endswith(suffix):
                return base[: -len(suffix)]
        return base

    def chat_url(self, base_url: str, model: str) -> str:
        # ``model`` is unused: it rides in the body here, not the path. The
        # parameter is part of the seam because Gemini puts it in the URL.
        return f"{self._root(base_url)}/api/chat"

    def headers(self, api_key: str) -> dict[str, str]:
        """Auth headers — none at all for a local server.

        A local Ollama checks nothing, so an empty key must produce no header
        rather than an empty ``Authorization``. Ollama Cloud does take a key
        (``OLLAMA_API_KEY``); the reference does not state the header it goes in,
        so the conventional bearer form is used and is **unverified** for Cloud.
        """
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    # ---- request -----------------------------------------------------------

    def _options(self, params: LlmParams, stop: list[str] | None) -> dict:
        """Sampler settings, under the names the native API uses.

        Ollama keeps every sampler in a nested ``options`` object rather than at
        the top level, and renames the one that matters most: OpenAI's
        ``max_tokens`` is ``num_predict``. Sent at the top level under its OpenAI
        name it is not rejected — unknown keys are dropped — so the cap simply
        does not apply and generation runs until the model stops on its own.

        ``num_ctx`` is sent only when someone has said what the window is — see
        ``context_window`` and the module docstring for why its absence is a silent
        truncation rather than an error. Hardcoding a number here would be worse
        than omitting it: the default is VRAM-tiered (4 K under 24 GiB, 32 K to
        48 GiB, 256 K above), so a fixed 4096 would *shrink* the window on a large
        box. The authoritative per-model figure is in ``/api/show``.
        """
        options: dict = {
            "temperature": params.temperature,
            "top_p": params.top_p,
            "num_predict": params.max_tokens,
        }
        if stop:
            options["stop"] = list(stop)
        window = _positive_int(self.context_window)
        if window:
            options["num_ctx"] = window
        elif self.context_window is not None:
            # A window that is not a positive int is a config error, and dropping
            # it quietly would reproduce the exact failure this attribute exists to
            # prevent: the request goes out, the server's smaller default applies,
            # and the prompt is cut with nothing to read afterwards.
            logger.debug(
                "ollama: ignoring unusable context_window=%r — num_ctx not sent",
                self.context_window,
            )
        # Ollama has exactly ONE repetition knob, ``options.repeat_penalty``: a
        # multiplicative penalty over the last ``repeat_last_n`` tokens, 1.0
        # meaning off. The reference's parameter-translation table maps
        # ``frequency_penalty`` onto it by name, and gives ``presence_penalty`` no
        # Ollama entry at all — so frequency is the translation, and presence is
        # honoured only when it is the one that was moved. Writing OpenAI's two
        # names into ``options`` instead (which is what this did until 2026-08-31)
        # is the worst outcome available: they are not Ollama option names,
        # unrecognised option keys are dropped without complaint, and so the
        # request succeeds, the slider does nothing, and nothing says so.
        #
        # Additive (-2…2, 0 = off) → multiplicative (>1 penalises, 1.0 = off) is an
        # approximation, not an identity. ``1 + penalty`` is chosen for the one
        # point that has to be exact — 0 in gives 1.0 out, so an untouched slider
        # changes nothing — and the clamp is a guard rather than a translation:
        # ``repeat_penalty`` scales logits, so a value at or below zero is
        # meaningless, and the top of OpenAI's range is degenerate in both
        # vocabularies anyway.
        penalty = params.frequency_penalty or params.presence_penalty
        if penalty:
            if params.frequency_penalty and params.presence_penalty:
                logger.debug(
                    "ollama: one repetition knob for two penalties — sending "
                    "frequency_penalty=%s as repeat_penalty, presence_penalty=%s unused",
                    params.frequency_penalty,
                    params.presence_penalty,
                )
            options["repeat_penalty"] = round(min(max(1.0 + float(penalty), 0.1), 2.0), 3)
        return options

    def _think(self, reasoning: ReasoningEffort | None) -> bool | str | None:
        """The ``think`` field, or ``None`` to leave the model's own default alone.

        ``NONE`` sends ``false`` rather than omitting the key: on a thinking-capable
        model, saying nothing means it thinks, which is exactly the cost
        ``ReasoningEffort.NONE`` exists to refuse (the structured engine's prose call
        was measured spending 91 % of its output on hidden reasoning).

        The level is always sent as a **string**, never ``True`` — ``think`` accepts
        a bool, but GPT-OSS requires the string form and a bool buys nothing here.

        Unverified: ``thinking`` is a per-model capability in ``/api/show``, and the
        reference does not say whether a model lacking it rejects ``think`` outright
        or ignores it. If it turns out to 400, this is where the capability check
        would have to be consulted.
        """
        if reasoning is None:
            return None
        if reasoning is ReasoningEffort.NONE:
            return False
        return _THINK_LEVELS.get(reasoning, "medium")

    def build_body(self, request: ChatRequest) -> dict:
        if not request.model:
            raise APIError(400, "bad_request", "A model is required to generate.")
        params = request.params or LlmParams()
        body: dict = {
            "model": request.model,
            # Roles and content match OpenAI's shape. Images differ — they are bare
            # base64 in an ``images`` array on the *message*, not content blocks and
            # not URLs — but ``ChatRequest.messages`` is text-only, so nothing here
            # has to carry that yet.
            "messages": [dict(m) for m in request.messages],
            # ``stream`` defaults to TRUE on /api/chat. A blocking caller that omits
            # it gets a newline-delimited sequence of objects where it expects one
            # JSON body, and json.loads() fails on the second line. Always explicit.
            "stream": bool(request.stream),
            "options": self._options(params, request.stop),
        }
        think = self._think(request.reasoning)
        if think is not None:
            body["think"] = think

        extra = dict(request.extra_body or {})
        fmt = _format_from_extra(extra)
        if fmt is not None:
            body["format"] = fmt
        # An escape-hatch ``options`` (num_ctx, seed, mirostat…) is merged into the
        # sampler block rather than replacing it — a plain update would drop
        # temperature and num_predict on the floor to set one key.
        extra_options = extra.pop("options", None)
        if isinstance(extra_options, dict):
            body["options"].update(extra_options)
        body.update(extra)
        return body

    # ---- reply -------------------------------------------------------------

    def parse_reply(self, payload: dict) -> ChatReply:
        """Read a blocking ``/api/chat`` reply, or a stream's final frame.

        Usage arrives as the eval-count pair: ``prompt_eval_count`` (input) and
        ``eval_count`` (output). Only the input figure is part of the normalised
        reply; ``eval_count`` and the nanosecond timings (``total_duration``,
        ``load_duration``, ``eval_duration`` — a cold start is visible in the second
        one) stay reachable in ``raw``.
        """
        if not isinstance(payload, dict):
            raise APIError(
                502, "upstream_error", "The model endpoint returned an unexpected payload."
            )
        error = _error_text(payload)
        if error:
            # Raised rather than returned as empty text: a ChatReply with text=""
            # is indistinguishable from a model that had nothing to say, and the
            # reason the endpoint gave would be thrown away at the one moment it
            # is the only useful thing in the payload. ``stream_payload`` raises
            # the same way on the same frame — see ``_error_text``.
            raise APIError(
                502, "upstream_error", f"Ollama rejected the request: {error[:200]}"
            )
        raw_message = payload.get("message")
        message = raw_message if isinstance(raw_message, dict) else {}
        return ChatReply(
            text=str(message.get("content") or ""),
            # Ollama's third name for the same channel. Reading llama.cpp's
            # ``reasoning_content`` or vLLM's ``reasoning`` here returns nothing,
            # which looks like a model that does not reason.
            reasoning=str(message.get("thinking") or ""),
            prompt_tokens=_positive_int(payload.get("prompt_eval_count")),
            # No cache split is reported — there is no counterpart to OpenAI's
            # ``prompt_tokens_details.cached_tokens``. Ollama does reuse a cached
            # prefix internally; it just does not say how much, so this stays None
            # rather than becoming a fabricated zero that reads as a cache miss.
            cached_tokens=None,
            raw=payload,
        )

    # ---- streaming ---------------------------------------------------------

    def stream_payload(self, line: str) -> dict | None:
        """One NDJSON line → its object, or ``None`` to skip. Raises on a failure frame.

        Beyond the ``ProviderAdapter`` protocol, which starts from a parsed event.
        The OpenAI path strips a ``data:`` prefix and watches for ``[DONE]``;
        neither exists here, so a shared line reader would silently yield nothing
        for every frame of a healthy stream.

        A ``{"error": …}`` line raises the same ``APIError`` ``parse_reply`` raises
        for the same object, because it *is* the same object — Ollama can send it
        mid-stream, after a 200 and after real content. Skipping it as
        unrecognised (which is what returning ``None`` here would mean) leaves a
        consumer accumulating nothing from a stream that will never end.
        """
        text = (line or "").strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except ValueError:
            return None
        if not isinstance(parsed, dict):
            return None
        error = _error_text(parsed)
        if error:
            raise APIError(
                502, "upstream_error", f"Ollama failed mid-stream: {error[:200]}"
            )
        return parsed

    def stream_delta(self, event: dict) -> str:
        message = event.get("message") if isinstance(event, dict) else None
        if not isinstance(message, dict):
            return ""
        return str(message.get("content") or "")

    def stream_reasoning(self, event: dict) -> str:
        """The thinking chunk on one streamed frame (beyond the protocol).

        The protocol's ``stream_delta`` returns visible text only, and the reasoning
        channel is streamed under ``message.thinking`` — a name no existing reader
        in this codebase checks.
        """
        message = event.get("message") if isinstance(event, dict) else None
        if not isinstance(message, dict):
            return ""
        return str(message.get("thinking") or "")

    def stream_done(self, event: dict) -> bool:
        """Whether this frame ends the stream.

        ``done`` is present and ``false`` on every intermediate frame, so its
        absence is not the signal — its truth is. The closing frame carries
        ``done_reason`` plus the eval counts and timings, and its
        ``message.content`` is **empty**: accumulate the text from the frames
        before it, or the reply is "".

        A failure frame also ends the stream, and it carries no ``done`` key at
        all. ``stream_payload`` raises on it first, so a consumer going through
        this adapter's line reader never reaches here with one; the case is
        covered anyway for a consumer driving the bare protocol off
        already-parsed events, because terminating with empty text beats waiting
        forever on a stream the server has stopped writing to.
        """
        if not isinstance(event, dict):
            return False
        return event.get("done") is True or bool(_error_text(event))

    # ---- discovery ---------------------------------------------------------

    def models_url(self, base_url: str) -> str:
        return f"{self._root(base_url)}/api/tags"

    def parse_models(self, payload: dict) -> list[str]:
        """Ids from ``/api/tags`` — and only ids, on purpose.

        This is one of the two backends where a single listing call is not enough.
        ``/api/tags`` reports name, size, digest and ``details`` (family,
        parameter_size, quantization_level) but neither capabilities nor context
        length; both live behind ``POST /api/show {"model": name}``, one request
        **per model**, with the window under an architecture-prefixed key
        (``model_info["general.architecture"]`` naming ``model_info[f"{arch}.context_length"]``)
        rather than a fixed field. A per-model POST does not fit the seam's
        one-GET ``models_url``/``parse_models`` pair, so the picker gets names and
        anything richer needs a call this adapter deliberately does not make.

        An empty list here means "nothing has been pulled yet", not "the server is
        broken" — the opposite of vLLM and llama.cpp, which each serve exactly one
        model and are genuinely unwell when they list none.
        """
        items = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return []
        names: list[str] = []
        for entry in items:
            if not isinstance(entry, dict):
                continue
            # ``name`` is the tagged id to pass back as ``model`` ("qwen3:8b").
            # ``model`` appears alongside it and has carried the same value; it is
            # a fallback only, never preferred.
            value = entry.get("name") or entry.get("model")
            if value:
                names.append(str(value))
        return names
