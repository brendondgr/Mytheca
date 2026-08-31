"""Google Gemini — the ``generateContent`` dialect.

Of the four backends this is the furthest from OpenAI's shape, and the
differences are almost all of the quiet kind. The model is in the URL path, not
the body. The container is ``contents``, not ``messages``. The assistant's role
is spelled ``model``. The sampler lives under ``generationConfig`` with renamed
keys. Thinking takes one of two mutually exclusive parameters chosen by model
generation, and sending both is a 400.

And the one that takes production down: **a blocked prompt returns HTTP 200 with
an empty ``candidates`` list.** The naive read — ``candidates[0]`` — raises
``IndexError``, which reads to a caller as a parser bug in Mytheca rather than a
safety refusal by Google. :func:`raise_if_blocked` is therefore the first thing
:meth:`GeminiAdapter.parse_reply` does, and it is public so the streaming path
can share it: a blocked *stream* also ends normally, with no text and no
exception — the same failure wearing a different hat.

The adapter is pure: it builds URLs, headers and bodies and reads payloads, and
performs no I/O, so every quirk below is testable without a network.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Final

from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort, budget_for
from app.schemas.settings import LlmParams
from app.services.llm_providers.base import (
    ChatReply,
    ChatRequest,
    normalize_base,
    split_system,
)

# Re-exported, not just imported: `raise_if_blocked`, `reply_parts` and `usage`
# were public on this module before the split and reading them off `gemini` is
# still correct.
from app.services.llm_providers.gemini_parse import (  # noqa: F401
    _candidates,
    _error_envelope,
    _first_candidate,
    _split_parts,
    raise_if_blocked,
    reply_parts,
    usage,
)

# Deliberately the same logger name ``services/llm.py`` and the OpenAI-compatible
# adapter already use. An operator debugging a generation filters on
# ``mytheca.llm``; a provider-private logger would put exactly the lines they are
# looking for outside that filter.
logger = logging.getLogger("mytheca.llm")

#: Unlike a local server there is exactly one host, so an unset base URL is a
#: default rather than a configuration error.
DEFAULT_BASE: Final = "https://generativelanguage.googleapis.com"

_API_VERSION: Final = "v1beta"
#: ``v1`` is stable, ``v1beta`` carries thinking + structured output, ``v1alpha``
#: is preview. An operator who pinned one keeps it.
_API_VERSIONS: Final = ("v1", "v1beta", "v1alpha")

#: Google's REST paths address a model as ``models/{id}``; the settings row and
#: the picker hold the bare id. Both spellings are tolerated on the way in so a
#: pasted ``models/gemini-3-pro`` cannot become ``/models/models/gemini-3-pro``.
_MODEL_PREFIX: Final = "models/"

#: ``finishReason`` values that end a generation NORMALLY. The reference states
#: the rule as an allowlist — raise unless the reason is ``STOP`` or
#: ``MAX_TOKENS`` (gemini.md §3) — and that direction is the load-bearing part:
#: Google keeps adding values (``LANGUAGE``, ``UNEXPECTED_TOOL_CALL``, ``OTHER``),
#: and under a denylist each new one returns an empty reply with no error, which
#: is the failure this module exists to prevent. ``MAX_TOKENS`` is normal here
#: because a truncation is better explained by the caller's empty-reply handling
#: than by a filter error.
#: The empty string is allowed too: a mid-stream frame carries no ``finishReason``
#: at all, and treating "not finished yet" as a failure would break every stream.

#: Four levels against Mytheca's six efforts. The collapse is at the top —
#: VERY_HIGH and MAX both land on ``high`` because nothing is above it — and NONE
#: lands on ``minimal`` because Gemini 3 has no "off": a caller wanting no
#: deliberation gets the least available, not silence.
_THINKING_LEVELS: Final[dict[ReasoningEffort, str]] = {
    ReasoningEffort.NONE: "minimal",
    ReasoningEffort.QUICK: "low",
    ReasoningEffort.LOW: "low",
    ReasoningEffort.MEDIUM: "medium",
    ReasoningEffort.HIGH: "high",
    ReasoningEffort.VERY_HIGH: "high",
    ReasoningEffort.MAX: "high",
}

#: 2.5-era ``thinkingBudget`` ranges, per family. Pro cannot disable thinking at
#: all — a 0 there is a 400, not a quiet no-op — and Flash-Lite floors at 512.
#: An id we cannot classify gets Pro's floor, because clamping a budget UP costs
#: latency while clamping it below a family's floor costs the whole call.
_BUDGET_RANGES: Final[dict[str, tuple[int, int]]] = {
    "flash-lite": (512, 24576),
    "flash": (0, 24576),
    "pro": (128, 32768),
}
_BUDGET_FALLBACK: Final = (128, 24576)

#: The REST reference caps ``stopSequences`` at five entries; our local reference
#: material does not restate the number (gemini.md §5 lists ``stop_sequences``
#: with no cap), so treat it as a bound worth respecting rather than a certainty.
#: Truncating loses a stop sequence; exceeding it loses the whole call to a 400.
#: Because the number is unverified, every truncation is logged at WARNING — if
#: the cap is wrong, the log is where that shows up instead of in a mystery.
_MAX_STOP_SEQUENCES: Final = 5

_GENERATION_RE: Final = re.compile(r"gemini[-_/]?(\d+)")

#: Keys a caller used to an OpenAI body may reach for to ask for streaming. None
#: of them exist here — the method and the ``?alt=sse`` parameter in the URL are
#: the whole mechanism — and Google rejects unknown fields, so letting one through
#: ``extra_body`` 400s a request that would otherwise have worked.
_BODY_LEVEL_STREAM_KEYS: Final = frozenset({"stream", "stream_options"})

#: ``assistant`` is not a role Gemini knows, and neither is ``tool``: a function
#: result is replayed on a **user** turn. An unmapped role is rejected outright,
#: and an accepted-but-wrong one would change who the model believes spoke.
_ROLES: Final[dict[str, str]] = {
    "assistant": "model",
    "model": "model",
    "user": "user",
    "tool": "user",
    "function": "user",
}


# ---- URLs -------------------------------------------------------------------


def _api_root(base_url: str) -> str:
    """The versioned API root, whatever the operator pasted into Options."""
    base = normalize_base(base_url or DEFAULT_BASE)
    tail = base.rsplit("/", 1)[-1]
    if tail == "openai":
        # The OpenAI-compatibility layer sits at /v1beta/openai/ and speaks a
        # different dialect entirely. Someone who pasted it wants Gemini, not a
        # 404 on .../openai/models/gemini-3-pro:generateContent.
        base = base.rsplit("/", 1)[0]
        tail = base.rsplit("/", 1)[-1]
    return base if tail in _API_VERSIONS else f"{base}/{_API_VERSION}"


def _model_id(model: str) -> str:
    name = (model or "").strip()
    if not name:
        raise APIError(400, "bad_request", "A model is required to generate.")
    return name[len(_MODEL_PREFIX) :] if name.startswith(_MODEL_PREFIX) else name


# ---- Request shaping --------------------------------------------------------


def _contents(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    """The ``contents`` array: role + parts, with same-role turns merged.

    Consecutive turns of one role are a normal result of Mytheca's assemblers.
    Rather than depend on an alternation rule we have not verified against a live
    endpoint, they fold into one ``Content`` with several parts, which is
    unambiguously valid.
    """
    out: list[dict[str, Any]] = []
    for message in messages:
        text = str(message.get("content") or "")
        signature = message.get("thoughtSignature") or message.get("thought_signature")
        if not text and not signature:
            continue
        role = _ROLES.get(str(message.get("role") or "user").strip().lower(), "user")
        part: dict[str, Any] = {"text": text}
        if signature:
            # Thought signatures are opaque encrypted state and must be replayed
            # BYTE FOR BYTE. Gemini 3 rejects a turn whose first functionCall
            # part comes back without the signature it was issued with, so a
            # signature that is dropped or "cleaned up" turns the next call of a
            # tool loop into a 400 with no hint of where it came from. The robust
            # form is to replay the model's returned parts verbatim — see
            # :func:`reply_parts` — this key is the string-only path for callers
            # that carry one field instead of the whole part.
            part["thoughtSignature"] = str(signature)
        if out and out[-1]["role"] == role:
            out[-1]["parts"].append(part)
        else:
            out.append({"role": role, "parts": [part]})
    return out


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _is_gemini_3(model: str) -> bool:
    match = _GENERATION_RE.search((model or "").lower())
    return int(match.group(1)) >= 3 if match else False


def _clamp_budget(model: str, budget: int) -> int:
    name = (model or "").lower()
    for family, bounds in _BUDGET_RANGES.items():
        if family in name:
            low, high = bounds
            break
    else:
        low, high = _BUDGET_FALLBACK
    return max(low, min(high, budget))


def _thinking_config(model: str, reasoning: ReasoningEffort | None) -> dict[str, Any]:
    """``thinkingLevel`` (3.x) or ``thinkingBudget`` (2.5.x) — never both.

    Sending both is a 400, which is the loud half. The quiet half is picking the
    wrong one: ``thinkingLevel`` is not a control 2.5 recognises, so an id we
    cannot classify falls back to ``thinkingBudget``, which 3.x still accepts for
    backward compatibility even though it is no longer the primary knob.

    ``None`` in returns ``{}``: unset means "leave the endpoint's own default
    alone", and that distinction is load-bearing all the way up — it is what
    keeps the structured engine's prose call at its own effort.
    """
    if reasoning is None:
        return {}
    if _is_gemini_3(model):
        return {
            "thinkingLevel": _THINKING_LEVELS.get(reasoning, "medium"),
            # Summaries only; the full internal reasoning is billed either way.
            # Without this the thought parts never arrive and the reasoning
            # channel is empty for a model that is demonstrably thinking.
            "includeThoughts": reasoning is not ReasoningEffort.NONE,
        }
    budget = _clamp_budget(model, budget_for(reasoning))
    # Keyed off the requested effort, not off the clamped budget: Pro and
    # Flash-Lite floor a NONE request above zero, and a caller that asked for no
    # deliberation must not start receiving thought summaries because of it.
    return {"thinkingBudget": budget, "includeThoughts": reasoning is not ReasoningEffort.NONE}


def _generation_config(request: ChatRequest) -> dict[str, Any]:
    """The renamed sampler block.

    ``max_tokens`` → ``maxOutputTokens``, ``top_p`` → ``topP``, ``stop`` →
    ``stopSequences``. Sent under their OpenAI names they are unknown fields, and
    Google's JSON parsing rejects unknown fields rather than ignoring them — so
    the failure here is at least a 400 and not a silently unbounded generation.
    """
    params = request.params or LlmParams()
    config: dict[str, Any] = {
        # Gemini's range is 0..2, the same as OpenAI's, so the stored value
        # passes through unscaled. Above 2 is a 400.
        "temperature": _clamp(params.temperature, 0.0, 2.0),
        "topP": _clamp(params.top_p, 0.0, 1.0),
        "maxOutputTokens": max(int(params.max_tokens), 1),
    }
    # NEITHER penalty is sent, at any value. pitfalls.md ("Temperature slider does
    # nothing on DeepSeek") says frequency_penalty and presence_penalty are
    # *globally* deprecated and never apply anywhere, and drops them; gemini.md §5
    # enumerates GenerateContentConfig and lists neither. So the only two outcomes
    # available were a 400 on an unknown field or — worse — a 200 where the slider
    # the operator moved does nothing and reads as broken.
    if params.frequency_penalty or params.presence_penalty:
        logger.debug(
            "gemini: dropping frequency/presence penalty (%s/%s) — deprecated, never applied",
            params.frequency_penalty,
            params.presence_penalty,
        )
    if request.stop:
        stops = [str(s) for s in request.stop]
        if len(stops) > _MAX_STOP_SEQUENCES:
            # Truncating silently changes what the generation does: a dropped
            # sequence simply stops stopping it, and the symptom (a reply running
            # past its terminator) points nowhere near this line. WARNING, not
            # debug — it is a request the caller made and is not getting.
            logger.warning(
                "gemini: dropping %d stop sequence(s) past the cap of %d: %r",
                len(stops) - _MAX_STOP_SEQUENCES,
                _MAX_STOP_SEQUENCES,
                stops[_MAX_STOP_SEQUENCES:],
            )
        config["stopSequences"] = stops[:_MAX_STOP_SEQUENCES]

    thinking = _thinking_config(request.model, request.reasoning)
    if thinking:
        config["thinkingConfig"] = thinking
        budget = thinking.get("thinkingBudget")
        if isinstance(budget, int) and budget > 0 and config["maxOutputTokens"] <= budget:
            # Thinking tokens are billed as output and spend the SAME budget as
            # the answer. A ceiling at or under the budget returns
            # ``finishReason: MAX_TOKENS`` with empty text — the model spent
            # everything thinking — which reads as "the model said nothing".
            # Only the numeric path can do this; ``thinkingLevel`` costs an
            # amount no client can know in advance.
            config["maxOutputTokens"] = int(config["maxOutputTokens"]) + budget
    return config


def _apply_schema(body: dict[str, Any], schema: Any) -> None:
    """Constrain output to JSON. Weakly — which the caller must know.

    Gemini is looser than OpenAI's strict mode: **unsupported schema keywords are
    silently ignored, not rejected.** A schema that "works" may be enforcing far
    less than it reads like (``oneOf`` is unsupported; string ``pattern`` is not
    documented as supported), so the parsed result still has to be validated
    client-side. ``responseJsonSchema`` takes standard JSON Schema — ``$ref``,
    recursion, ``anyOf`` — where ``responseSchema`` takes the narrower OpenAPI
    subset; only ONE of the two may be set or the request is rejected.
    """
    if not isinstance(schema, dict):
        return
    config = _apply_json_mode(body)
    config.pop("responseSchema", None)
    config["responseJsonSchema"] = schema


def _apply_json_mode(body: dict[str, Any]) -> dict[str, Any]:
    """JSON output with no schema — OpenAI's ``{"type": "json_object"}``.

    Schema-less JSON mode is weaker than a schema, but it is what the caller
    asked for and it is a shape Gemini has: ``responseMimeType`` alone. Dropping
    it instead (which this adapter did) is the worst outcome on the board —
    decoding stays completely unconstrained, the call SUCCEEDS, and the failure
    surfaces much later as "the model wrote prose where JSON was expected", with
    nothing pointing back at the provider seam. ``ollama.py`` handles the same
    shape by mapping it onto ``format: "json"``.
    """
    config = body.setdefault("generationConfig", {})
    config["responseMimeType"] = "application/json"
    return config


def _apply_extra(body: dict[str, Any], extra: dict) -> None:
    """Fold ``extra_body`` in, translating the two dialects callers already send.

    Mytheca's structured-output call sites were written against OpenAI
    (``response_format``) and vLLM (``guided_json``); passed through untouched
    they are unknown fields and the call 400s. Anything else goes through as-is —
    a caller reaching for a Gemini-shaped key (``safetySettings``, ``tools``,
    ``cachedContent``) is what the escape hatch is for.
    """
    for key, value in extra.items():
        if key == "generationConfig" and isinstance(value, dict):
            body.setdefault("generationConfig", {}).update(value)
        elif key == "response_format" and isinstance(value, dict):
            nested = value.get("json_schema")
            schema = nested.get("schema") if isinstance(nested, dict) else None
            if isinstance(schema, dict):
                _apply_schema(body, schema)
            elif value.get("type") in ("json_object", "json_schema"):
                # A schema-less ``json_object`` (and a ``json_schema`` whose schema
                # did not survive) still asks for JSON. See :func:`_apply_json_mode`
                # for why dropping it is worse than honouring it weakly.
                _apply_json_mode(body)
        elif key == "guided_json":
            _apply_schema(body, value)
        elif key in _BODY_LEVEL_STREAM_KEYS:
            # OpenAI habits that are unknown fields here, and Google's parser
            # rejects unknown fields rather than ignoring them: passed through,
            # they 400 the whole call. Streaming is a URL method on this provider
            # — see :meth:`GeminiAdapter.chat_url`.
            logger.warning(
                "gemini: dropping body key %r — streaming rides in the URL, not the body", key
            )
        else:
            body[key] = value


# ---- The adapter ------------------------------------------------------------


class GeminiAdapter:
    """Google's Gemini Developer API (``generativelanguage.googleapis.com``)."""

    id: str = "gemini"
    label: str = "Google Gemini"

    #: The llama.cpp symptom — a stop sequence matching inside the REASONING
    #: channel and killing the generation mid-thought — has no analogue here:
    #: ``stopSequences`` applies to the emitted answer, and thinking is returned
    #: as separate parts flagged ``thought`` rather than as the same stream. Note
    #: this is structural reasoning, NOT a measurement against a live endpoint;
    #: if a stop sequence is ever seen truncating a Gemini reply mid-thought,
    #: this flag is the thing to flip.
    stop_matches_reasoning: bool = False

    streaming_dispatched: bool = True

    #: ``?alt=sse`` is what makes this an event stream. Without it the same
    #: endpoint answers with a single JSON array, which parses as one enormous
    #: frame at the end — a "stream" that types nothing.
    stream_media_types: tuple[str, ...] = ("event-stream",)

    #: Prefilled when an operator switches to this provider and has no URL yet.
    #: A blank field beside a provider that only ever has one endpoint is a
    #: question with one right answer, asked for no reason.
    default_base_url: str = DEFAULT_BASE

    def chat_url(self, base_url: str, model: str, *, stream: bool = False) -> str:
        """``…/v1beta/models/{model}:generateContent``.

        The model rides in the PATH, not the body — a ``"model"`` key in the body
        is an unknown field, and a URL built without it addresses no model at all.

        The streaming variant is a different METHOD, ``:streamGenerateContent``,
        and it needs ``?alt=sse``: without that parameter the endpoint streams a
        JSON *array* rather than SSE frames, so a line-oriented SSE reader sees
        no events at all and the call looks like a stream that produced nothing.

        **What a caller must do.** ``stream`` is keyword-only with a default
        because :class:`~app.services.llm_providers.base.ProviderAdapter` declares
        ``chat_url(base_url, model)`` and the two-argument call has to keep
        working; ``False`` is the safe default, since a blocking read of a
        blocking endpoint is right, while a blocking read of an SSE endpoint is a
        hang. Every other provider carries the flag in the body, so a dispatcher
        that only sets ``ChatRequest.stream`` streams correctly everywhere except
        here. Rather than leave that to be remembered, use :meth:`chat_target`,
        which takes the request and returns the URL and the body together.
        """
        method = "streamGenerateContent?alt=sse" if stream else "generateContent"
        return f"{_api_root(base_url)}/models/{_model_id(model)}:{method}"

    def chat_target(self, base_url: str, request: ChatRequest) -> tuple[str, dict]:
        """``(url, body)`` for one request — the pair that must not disagree.

        The whole of Gemini's streaming switch lives in the URL, and the URL is
        built from arguments (``base_url``, ``model``) that carry no trace of it.
        Split across two calls, the mismatch is silent in the worst direction: a
        ``stream=True`` request POSTed to ``:generateContent`` returns one JSON
        body, the SSE reader sees zero frames, and the turn ends with no text and
        no error.

        Beyond the Protocol, deliberately: widening ``chat_url`` with a required
        argument would break the other three adapters, so this is the additive
        way to give a dispatcher one call that cannot be got wrong.
        """
        return (
            self.chat_url(base_url, request.model, stream=bool(request.stream)),
            self.build_body(request),
        )

    def headers(self, api_key: str) -> dict[str, str]:
        """Key in a header. Never ``?key=`` in the URL.

        The query-string form most Gemini snippets use leaks the secret into
        access logs, proxy logs, browser history and ``Referer`` headers;
        Mytheca's safety rules forbid secrets in query strings outright. A missing
        key fails loudly (401/403, "API key not valid").
        """
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["x-goog-api-key"] = api_key
        return headers

    def build_body(self, request: ChatRequest) -> dict:
        """``contents`` + ``systemInstruction`` + ``generationConfig``.

        Nothing in the body says "stream" — that is the URL's job, and it is the
        one difference from the other three adapters, whose ``build_body`` all
        write ``request.stream`` into the body. A ``"stream": true`` key here is
        an unknown field, and Google's parser rejects unknown fields rather than
        ignoring them, so writing one would 400 every streamed call. The flag is
        therefore read here only to keep the two halves honest: any body-level
        streaming key smuggled in through ``extra_body`` is dropped and logged,
        and a streaming request leaves a breadcrumb naming the URL method it
        needs. The pairing itself is :meth:`chat_target`'s job.
        """
        system, turns = split_system(request.messages)
        contents = _contents(turns)
        if not contents:
            # Gemini requires a non-empty `contents`; a system-only call is
            # rejected with a message about a field the caller never set.
            raise APIError(
                400, "bad_request", "Gemini needs at least one user or model message."
            )
        body: dict[str, Any] = {"contents": contents}
        if system:
            # A `system` ROLE would be rejected here, and the base module's
            # warning applies in full: the prompt has to leave `contents` or it
            # is not the system instruction at all.
            body["systemInstruction"] = {"parts": [{"text": system}]}
        body["generationConfig"] = _generation_config(request)
        if request.extra_body:
            _apply_extra(body, dict(request.extra_body))
        if request.stream:
            # The half of the request this method cannot satisfy, said out loud.
            # If a stream ever comes back as a single JSON blob, this line and the
            # URL beside it in the log are what identify the caller that built the
            # body from the request but the URL from a bare model id.
            logger.debug(
                "gemini: streaming request built; the URL must use "
                ":streamGenerateContent?alt=sse (chat_target does this)"
            )
        return body

    def parse_reply(self, payload: dict) -> ChatReply:
        # Before any candidates[0] read. See its docstring.
        raise_if_blocked(payload)
        text, reasoning = _split_parts(payload)
        prompt_tokens, cached_tokens = usage(payload)
        return ChatReply(
            text=text,
            reasoning=reasoning,
            prompt_tokens=prompt_tokens,
            cached_tokens=cached_tokens,
            # A reply and a stream frame are the same shape here, so the frame
            # reader answers for both.
            finish_reason=self.stream_finish_reason(payload),
            raw=payload if isinstance(payload, dict) else {},
        )

    def models_url(self, base_url: str) -> str:
        return f"{_api_root(base_url)}/models"

    def parse_models(self, payload: dict) -> list[str]:
        """``models[].name`` with the ``models/`` prefix stripped.

        Not ``data[].id``. Read the OpenAI shape against this payload and the
        picker is empty for a perfectly healthy endpoint.

        Entries that cannot serve a chat call (embedding models, ``aqa``) are
        dropped when the response says so — the SDK calls the field
        ``supported_actions`` while REST returns ``supportedGenerationMethods``,
        so both are checked and an entry carrying neither is KEPT: filtering on a
        field that turns out to be absent would empty the picker, which is the
        failure this method exists to avoid. One page only — a ``nextPageToken``
        means the catalogue is longer, and following it is the caller's job.
        """
        models = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            return []
        out: list[str] = []
        for entry in models:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if not isinstance(name, str) or not name:
                continue
            methods = entry.get("supportedGenerationMethods") or entry.get("supported_actions")
            if isinstance(methods, list) and methods and "generateContent" not in methods:
                continue
            out.append(name[len(_MODEL_PREFIX) :] if name.startswith(_MODEL_PREFIX) else name)
        return out

    def parse_stream_line(self, line: str) -> dict | None:
        """One ``alt=sse`` line -> its ``GenerateContentResponse``, or ``None``.

        Each frame is a whole response object rather than a delta, so the value
        returned here is the same shape :meth:`parse_reply` reads. There is no
        ``[DONE]`` sentinel: :meth:`stream_done` reads ``finishReason`` instead.
        """
        line = (line or "").strip()
        if not line.startswith("data:"):
            return None
        data = line[len("data:") :].strip()
        if not data:
            return None
        try:
            parsed = json.loads(data)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def stream_usage(self, event: dict) -> tuple[int | None, int | None]:
        """``usageMetadata`` off one frame.

        Gemini repeats the cumulative counts on **every** frame rather than
        sending one trailing usage frame, so the last value read wins and there
        is nothing special to do at the end of the stream.
        """
        if not isinstance(event, dict):
            return None, None
        return usage(event)

    def stream_finish_reason(self, event: dict) -> str | None:
        """``candidates[0].finishReason`` — ``MAX_TOKENS`` where OpenAI says ``length``."""
        if not isinstance(event, dict):
            return None
        reason = _first_candidate(event).get("finishReason")
        return str(reason) if reason else None

    def stream_delta(self, event: dict) -> str:
        """The answer text in one SSE frame — thought parts excluded.

        Each frame is a whole ``GenerateContentResponse``, not an OpenAI-style
        delta object, so the text lives at ``candidates[0].content.parts[]`` in
        every frame rather than under ``choices[0].delta``. A frame with no
        candidates (a block, or a usage-only tail) yields "" rather than raising:
        the dispatcher decides what an empty stream means, via
        :func:`raise_if_blocked`.
        """
        answer, _ = _split_parts(event)
        return answer

    def stream_reasoning(self, event: dict) -> str:
        """The thought-summary text in one frame.

        Not part of the base protocol, which has one text channel per event. The
        alternatives were folding thought parts into :meth:`stream_delta` —
        printing the model's deliberation into the scene — or dropping the
        channel, which looks like "this model does no reasoning". A dispatcher
        that ignores this method loses only the live thinking display.
        """
        _, thoughts = _split_parts(event)
        return thoughts

    def stream_done(self, event: dict) -> bool:
        """Whether this frame ends the stream.

        There is no ``[DONE]`` sentinel: the stream ends when the connection
        closes, and the last frame carries a ``finishReason``. A first-and-only
        frame that reports a blocked prompt has no candidates and no
        ``finishReason``, and is also the end — treating that as "keep reading"
        hangs the reader until the timeout.

        A frame whose ``candidates`` is not a list at all is read the same way as
        one with none — via :func:`_candidates` — so a mangled frame cannot be a
        ``TypeError`` here while :func:`reply_parts` handles it calmly.
        """
        if not isinstance(event, dict):
            return False
        if not _candidates(event):
            feedback = event.get("promptFeedback")
            if isinstance(feedback, dict) and feedback.get("blockReason"):
                return True
            # An error envelope in a 200 stream is also the end: nothing more is
            # coming, and waiting for a finishReason that will never arrive hangs
            # the reader until the timeout.
            return bool(_error_envelope(event))
        return bool(_first_candidate(event).get("finishReason"))
