"""Anthropic (Claude) — the Messages API dialect.

Every difference encoded here fails the way ``base`` warns about: quietly, or
with a 400 that names something other than the real cause.

* ``system`` is a top-level parameter, and there is no ``system`` role at all.
  The reference is explicit that leaving one in ``messages`` is a **400**, not a
  quiet downgrade — so this particular mistake fails loudly and every call
  fails, rather than the world primer and the output contract vanishing into a
  200 that merely reads worse. (``base.split_system`` says "ignored, with a
  200"; that claim is wrong for this provider and is not this file's to fix.)
* ``max_tokens`` is required and covers *thinking plus visible output*, so a
  thinking call sized for prose alone returns an empty passage.
* Reply content is a list of typed blocks, not a ``message.content`` string.
* Usage counts cached input **additively**, the opposite of OpenAI, so the
  naive read under-reports context by the whole cached prefix.
* Streaming is typed SSE events with no ``[DONE]`` sentinel.

The adapter is pure: it builds URLs, headers and bodies and reads payloads. It
holds no state and performs no network I/O — the single exception to its silence
is a log line when it has to invent a number a caller got wrong, which beats
correcting one behind their back. That purity is why the two live signals —
the model's thinking mode and its own ``max_tokens`` ceiling — are handled by
documented defaults plus an ``extra_body`` override rather than by guessing from
a version string.
"""

from __future__ import annotations

import json
import logging
from copy import deepcopy

from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort, budget_for
from app.schemas.settings import LlmParams
from app.services.llm_providers.base import (
    ChatReply,
    ChatRequest,
    normalize_base,
    split_system,
)

#: Shared with the OpenAI-compatible adapter so one filter shows the whole seam.
logger = logging.getLogger("mytheca.llm")

#: Anthropic is a hosted service at one address, so an operator has nothing
#: useful to type here. Used when the settings row's base URL is blank, which
#: would otherwise raise out of ``normalize_base`` for a perfectly valid config.
DEFAULT_BASE_URL = "https://api.anthropic.com"

#: Sent as ``anthropic-version``. The header is mandatory — omitting it is a 400
#: that complains about the version rather than about the request you changed.
#: The reference does not state a value; this is the long-standing GA string for
#: the Messages API. It is pinned deliberately: tracking "latest" would let a
#: server-side change alter behaviour with no commit in this repo to blame.
API_VERSION = "2023-06-01"

#: Manual-mode floor stated by the reference. A smaller ``budget_tokens`` is a
#: 400, which matters because Mytheca's own ladder starts at 128.
MIN_THINKING_BUDGET = 1024

#: Mytheca's seven-rung effort ladder onto the five levels adaptive thinking
#: accepts. ``NONE`` is absent on purpose: it means *do not think*, which on this
#: API is expressed by sending no ``thinking`` field at all.
_ADAPTIVE_EFFORT: dict[ReasoningEffort, str] = {
    ReasoningEffort.QUICK: "low",
    ReasoningEffort.LOW: "low",
    ReasoningEffort.MEDIUM: "medium",
    ReasoningEffort.HIGH: "high",
    ReasoningEffort.VERY_HIGH: "xhigh",
    ReasoningEffort.MAX: "max",
}


class AnthropicAdapter:
    """The Anthropic Messages dialect. Stateless; construct once, reuse."""

    id: str = "anthropic"
    label: str = "Anthropic (Claude)"

    #: The llama.cpp symptom (a stop sequence matching the hidden channel and
    #: killing the generation mid-thought) does not apply here: deliberation
    #: arrives as its own ``thinking`` block and ``stop_sequences`` is documented
    #: against the response text. Not measured on this stack — inherited from the
    #: reference's channel separation, so treat a mid-thought truncation on
    #: Anthropic as evidence against this flag rather than as impossible.
    stop_matches_reasoning: bool = False

    streaming_dispatched: bool = True

    stream_media_types: tuple[str, ...] = ("event-stream",)

    #: Prefilled when an operator switches to this provider and has no URL yet.
    #: A blank field beside a provider that only ever has one endpoint is a
    #: question with one right answer, asked for no reason.
    default_base_url: str = DEFAULT_BASE_URL

    # ---- Transport ---------------------------------------------------------

    def chat_url(self, base_url: str, model: str, *, stream: bool = False) -> str:
        # The model rides in the body and ``"stream": true`` asks for the
        # stream, so neither argument changes the path. One endpoint, both ways.
        return f"{_base(base_url)}/v1/messages"

    def models_url(self, base_url: str) -> str:
        return f"{_base(base_url)}/v1/models"

    def headers(self, api_key: str) -> dict[str, str]:
        """``x-api-key``, **not** ``Authorization: Bearer``.

        A Bearer token is a 401 that reads like a bad key, so an operator who
        pasted a perfectly good key spends the afternoon regenerating it.
        """
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": API_VERSION,
        }
        if api_key:
            headers["x-api-key"] = api_key
        return headers

    # ---- Request -----------------------------------------------------------

    def build_body(self, request: ChatRequest) -> dict:
        if not request.model:
            raise APIError(400, "bad_request", "A model is required to generate.")
        p = request.params or LlmParams()
        system, messages = split_system(request.messages)
        if not messages:
            # Every prompt in this codebase pairs a system message with a user
            # one, but a call site that sends only a system message would hoist
            # it away and post an empty list — a 400 about ``messages`` that
            # says nothing about the prompt that caused it.
            raise APIError(
                400,
                "bad_request",
                "Anthropic needs at least one user message; this prompt is system-only.",
            )

        visible_tokens = max(int(p.max_tokens), 1)
        body: dict = {
            "model": request.model,
            "messages": messages,
            # Required, and there is no default: omit it and every call 400s.
            "max_tokens": visible_tokens,
            # 0..1 here, not OpenAI's 0..2. An operator who saved 1.5 for a local
            # model gets a 400 on every generation the moment they switch
            # provider, so the stored value is clamped rather than passed on.
            "temperature": min(max(float(p.temperature), 0.0), 1.0),
        }
        if system:
            # Top-level, because this API has no ``system`` role: the reference
            # states that a ``{"role": "system"}`` entry left in ``messages`` is
            # a 400. ``base.split_system`` hoisted it above; do not trust that
            # function's docstring on the consequence — it says "ignored, with a
            # 200", which is not what this provider does.
            body["system"] = system
        if p.top_p < 1.0:
            # 1.0 is a no-op, and the reference does not say whether sending
            # ``top_p`` alongside ``temperature`` is accepted or rejected here.
            # Sending only the sampler the operator actually moved avoids
            # depending on the answer.
            body["top_p"] = p.top_p
        # ``frequency_penalty`` / ``presence_penalty`` have no equivalent on this
        # API and are dropped, not translated. That is correct — there is nothing
        # to translate them into — but it is silent, so a scene tuned against a
        # local model with penalties dialled in will read differently here.
        if request.stop:
            body["stop_sequences"] = list(request.stop)  # not ``stop``
        if request.stream:
            body["stream"] = True
            # No ``stream_options``: that is an OpenAI field and Anthropic
            # rejects it. Usage arrives on the ``message_start`` /
            # ``message_delta`` events instead — see :meth:`parse_usage`.

        thinking, headroom = _thinking_fields(request.reasoning)
        if thinking:
            body.update(thinking)
            # Thinking tokens are billed as output and spent out of the SAME
            # ``max_tokens``. Sized for prose alone, the model spends the whole
            # allowance deliberating and returns ``stop_reason: "max_tokens"``
            # with empty content — a blank beat, no error anywhere. The operator's
            # number is the *visible* budget, so the thinking room is added on top.
            body["max_tokens"] = visible_tokens + headroom

        if request.extra_body:
            # Applied last so it can override the thinking config, which is the
            # only route to manual mode (see :func:`_thinking_fields`).
            #
            # DEEP-COPIED, because ``dict.update`` copies references: without it
            # ``body["thinking"]`` would *be* the caller's own nested dict, and
            # the budget repair below would rewrite the caller's object rather
            # than the request. ``ChatRequest`` is frozen, but freezing a
            # dataclass freezes the field, not the dict the field points at — so
            # one extra_body template reused across a retry or a provider
            # fallback chain would come back from the first call already edited,
            # and the second call would be shaped by the first.
            body.update(deepcopy(request.extra_body))
        # Runs AFTER the merge, because only the merged body knows which
        # thinking mechanism is actually going on the wire.
        _fit_manual_thinking(body, visible_tokens)
        return body

    # ---- Reply -------------------------------------------------------------

    def parse_reply(self, payload: dict) -> ChatReply:
        """Read a Messages reply, whose ``content`` is a LIST of typed blocks.

        There is no ``message.content`` string and no ``choices``. Reading either
        yields an empty completion rather than an error.
        """
        blocks = payload.get("content") if isinstance(payload, dict) else None
        text_parts: list[str] = []
        thinking_parts: list[str] = []
        for block in blocks if isinstance(blocks, list) else []:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "text":
                text_parts.append(str(block.get("text") or ""))
            elif kind == "thinking":
                thinking_parts.append(str(block.get("thinking") or ""))
            # ``redacted_thinking`` carries opaque ciphertext in ``data``. It is
            # deliberately not decoded into the reasoning channel — it is not
            # text, and rendering it would put base64 in front of the player.
        prompt_tokens, cached_tokens = self.parse_usage(payload)
        return ChatReply(
            # One passage split across blocks is still one passage, so the text
            # joins with nothing; separate deliberations are separate thoughts.
            text="".join(text_parts),
            reasoning="\n\n".join(part for part in thinking_parts if part),
            prompt_tokens=prompt_tokens,
            cached_tokens=cached_tokens,
            finish_reason=self.stream_finish_reason(payload),
            raw=payload if isinstance(payload, dict) else {},
        )

    def parse_usage(self, payload: dict) -> tuple[int | None, int | None]:
        """``(prompt_tokens, cached_tokens)`` from a reply **or** a stream event.

        Two traps in one place:

        1. The field is ``input_tokens``, not ``prompt_tokens``. Read the wrong
           name and the context dial goes blank with no error.
        2. Anthropic's cache counts are **additive** — the total the model saw is
           ``input_tokens + cache_creation_input_tokens + cache_read_input_tokens``
           — whereas OpenAI's ``cached_tokens`` is a subset already inside
           ``prompt_tokens``. Passing ``input_tokens`` straight through therefore
           under-reports by the entire cached prefix, and does so *more* as the
           scene grows and caching does more work: the dial falls while the real
           context climbs.

        Accepts a ``message_start`` event too, where the same object is nested
        under ``message``.
        """
        if not isinstance(payload, dict):
            return None, None
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            message = payload.get("message")
            usage = message.get("usage") if isinstance(message, dict) else None
        if not isinstance(usage, dict):
            return None, None
        base = _count(usage.get("input_tokens"))
        if base is None:
            # ``message_delta`` reports only the output side; there is nothing to
            # correct a prompt figure with, so report nothing rather than a zero.
            return None, None
        cached = _count(usage.get("cache_read_input_tokens"))
        created = _count(usage.get("cache_creation_input_tokens"))
        total = base + (cached or 0) + (created or 0)
        return (total or None), cached

    def parse_models(self, payload: dict) -> list[str]:
        """Model ids from ``GET /v1/models``.

        The reference documents the item shape (``id``, ``display_name``,
        ``max_tokens``, ``capabilities``) and the pagination fields
        (``has_more`` / ``first_id`` / ``last_id``) but does not name the array
        key, so :func:`_model_items` accepts both spellings rather than guessing
        one.

        Only the first page is returned: a pure adapter cannot follow
        ``last_id``. If the account ever exposes more models than one page holds,
        the picker will look short — check ``has_more`` in the raw payload before
        concluding a model is unavailable.
        """
        return [
            str(m.get("id")) if isinstance(m, dict) else str(m)
            for m in _model_items(payload)
            if (isinstance(m, dict) and m.get("id")) or isinstance(m, str)
        ]

    # ---- Streaming ---------------------------------------------------------

    def stream_delta(self, event: dict) -> str:
        """The visible text carried by one typed SSE event.

        Anthropic streams named events — ``message_start``,
        ``content_block_start``, ``content_block_delta``, ``content_block_stop``,
        ``message_delta``, ``message_stop``, plus ``ping`` throughout — and each
        ``data:`` payload repeats its name in ``type``. There is no
        ``choices[0].delta.content`` anywhere in that sequence; a consumer
        looking for one streams silence and then reports an empty completion.

        ``thinking_delta`` returns "" rather than its text — deliberately, and
        it is not lost: it arrives on :meth:`stream_reasoning`, the seam's
        second channel. Folding it in here would print the model's private
        reasoning into the scene as prose.
        """
        if not isinstance(event, dict) or event.get("type") != "content_block_delta":
            return ""
        delta = event.get("delta")
        if not isinstance(delta, dict) or delta.get("type") != "text_delta":
            # ``thinking_delta`` (hidden), ``signature_delta`` (one opaque token
            # of provenance before a thinking block closes) and
            # ``input_json_delta`` (tool arguments, which Mytheca does not use)
            # all land here.
            return ""
        return str(delta.get("text") or "")

    def parse_stream_line(self, line: str) -> dict | None:
        """One SSE line -> its JSON payload, or ``None`` to skip.

        Anthropic's stream carries BOTH an ``event:`` name line and a ``data:``
        payload line for every event, plus blank separators and periodic
        ``ping``s. Only the payload is read — the name is repeated inside it as
        ``type``, which is what every method below dispatches on.

        There is no ``[DONE]`` sentinel to translate; :meth:`stream_done` reads
        the typed ``message_stop`` instead.
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

    def stream_reasoning(self, event: dict) -> str:
        """The ``thinking_delta`` text on one event ("" for anything else).

        ``signature_delta`` is excluded: it is one opaque provenance token, not
        thought, and rendering it would put base64 in the thinking pane.
        """
        if not isinstance(event, dict) or event.get("type") != "content_block_delta":
            return ""
        delta = event.get("delta")
        if not isinstance(delta, dict) or delta.get("type") != "thinking_delta":
            return ""
        return str(delta.get("thinking") or "")

    def stream_usage(self, event: dict) -> tuple[int | None, int | None]:
        """The token counts on ``message_start`` (and the tail ``message_delta``).

        Delegates to :meth:`parse_usage`, which already reads the nested
        ``message.usage`` shape a ``message_start`` uses — the input side is
        reported ONCE, at the very beginning, unlike OpenAI's trailing frame.
        """
        if not isinstance(event, dict):
            return None, None
        if event.get("type") not in ("message_start", "message_delta"):
            return None, None
        return self.parse_usage(event)

    def stream_finish_reason(self, event: dict) -> str | None:
        """``delta.stop_reason`` from the tail ``message_delta``.

        Anthropic says ``max_tokens`` where OpenAI says ``length``; the caller
        compares case-insensitively against both, so the raw value is passed
        through rather than translated into a foreign vocabulary here.
        """
        if not isinstance(event, dict):
            return None
        if event.get("type") == "message_delta":
            delta = event.get("delta")
            reason = delta.get("stop_reason") if isinstance(delta, dict) else None
            if reason:
                return str(reason)
        reason = event.get("stop_reason")
        return str(reason) if reason else None

    def stream_done(self, event: dict) -> bool:
        """Whether this event ends the stream.

        There is no ``data: [DONE]`` sentinel — the terminator is a typed
        ``message_stop``. A loop waiting for OpenAI's sentinel hangs until the
        read timeout and then reports the endpoint as unreachable.

        An ``error`` event can also arrive **mid-stream, after a 200** (usually
        ``overloaded_error``), and no ``message_stop`` follows it. It is treated
        as terminal so the consumer stops rather than waiting out the timeout.
        The seam carries no error channel, so the caller sees a short or empty
        completion; the event's ``error.type`` is worth logging at the call site
        to tell "overloaded" apart from "the model finished early".
        """
        if not isinstance(event, dict):
            return False
        return event.get("type") in ("message_stop", "error")


# ---- Helpers ---------------------------------------------------------------


def _base(base_url: str) -> str:
    """Normalise the base URL and strip a trailing ``/v1``.

    The OpenAI-compatible field next door wants the ``/v1`` included, so it gets
    pasted in here out of habit — and ``/v1/v1/messages`` is a 404 that looks
    like a wrong endpoint rather than a doubled path segment.

    The fallback is tested against the STRIPPED value. ``normalize_base`` strips
    before it decides a URL is empty, so ``" "`` — what a settings row holds
    after someone selects the old URL and hits space — reached it as truthy and
    raised "a base URL is required" for the one provider where there is nothing
    to type, which is precisely the config :data:`DEFAULT_BASE_URL` exists to
    rescue.
    """
    base = normalize_base((base_url or "").strip() or DEFAULT_BASE_URL)
    return base[: -len("/v1")] if base.endswith("/v1") else base


def _thinking_fields(reasoning: ReasoningEffort | None) -> tuple[dict, int]:
    """``(body fields, output headroom)`` for a thinking call.

    Two mechanisms exist and **picking the wrong one is a 400 either way**:

    * ``thinking={"type": "adaptive"}`` + ``output_config={"effort": ...}`` is
      current, and is rejected on models that predate it.
    * ``thinking={"type": "enabled", "budget_tokens": N}`` is the original, is
      deprecated on the 4.6 generation and is rejected on 4.7+ with
      ``"thinking.type.enabled" is not supported for this model``.

    The correct signal is whether the model advertises an ``effort`` ladder in
    its capabilities (see :func:`effort_capable_models`) — the reference is
    explicit that routing on a version string is the wrong move. A pure adapter
    cannot fetch capabilities, so the default here is **adaptive**, which is
    right for every currently-shipping model, and manual mode is reached by
    passing ``thinking``/``output_config`` through ``ChatRequest.extra_body``.

    ``None`` in means "leave the provider's own default alone" — which on this
    API is thinking off — and so does ``NONE``, explicitly.
    """
    if reasoning is None or reasoning is ReasoningEffort.NONE:
        return {}, 0
    effort = _ADAPTIVE_EFFORT.get(reasoning, _ADAPTIVE_EFFORT[ReasoningEffort.MEDIUM])
    # Adaptive mode sends no token budget — the model decides. The ladder's
    # budget is still used as *output headroom*, because the thinking the model
    # chooses to do is spent from ``max_tokens`` either way.
    headroom = max(budget_for(reasoning), MIN_THINKING_BUDGET)
    return {"thinking": {"type": "adaptive"}, "output_config": {"effort": effort}}, headroom


def _fit_manual_thinking(body: dict, visible_tokens: int) -> None:
    """Make a body that asked for MANUAL thinking internally consistent.

    Only reachable via ``extra_body``, and only after the merge — so this is the
    one place that sees which of the two mechanisms is really going on the wire.

    **The adaptive leftovers have to go.** :func:`_thinking_fields` writes the
    adaptive pair ``thinking`` + ``output_config``, and ``dict.update`` can
    replace ``thinking`` but has no way to *delete* the sibling it no longer
    belongs to. A caller who switched to manual through the documented escape
    hatch would otherwise ship both mechanisms at once: ``output_config``'s
    ``effort`` is how adaptive mode is steered and ``budget_tokens`` is how
    manual mode is, and the reference presents them as alternatives, never as
    layers. ``output_config`` is dropped even when the caller passed it
    explicitly — a body naming two different depth controls has no honest
    reading, and dropping it is at worst the same 400 the caller was already
    heading for.

    Manual mode also requires ``budget_tokens`` of at least 1024 and normally
    strictly below ``max_tokens``; a caller who sets a 10k budget against this
    app's 512-token default gets a 400 naming neither number.

    Sampling parameters are rejected alongside manual thinking, so they are
    stripped here. The reference states that constraint for manual mode only —
    whether adaptive mode also rejects them is **not** covered by the reference,
    so temperature and top_p are left in place for adaptive rather than dropped
    on a guess (silently generating at the wrong temperature would be worse than
    a loud 400 that tells us to drop them).
    """
    thinking = body.get("thinking")
    if not isinstance(thinking, dict) or thinking.get("type") != "enabled":
        return
    body.pop("output_config", None)  # adaptive-only — see above
    body.pop("temperature", None)
    body.pop("top_p", None)

    budget = _budget_tokens(thinking.get("budget_tokens"))
    if budget is None:
        # Absent, negative, or a shape no int can be read out of. The floor is
        # the only number the reference licenses inventing, and inventing it
        # silently is how a 10k request becomes a 1024 one with nobody the wiser.
        logger.warning(
            "Anthropic manual thinking: no usable budget_tokens (%r); "
            "sending the documented floor of %d instead.",
            thinking.get("budget_tokens"),
            MIN_THINKING_BUDGET,
        )
        budget = MIN_THINKING_BUDGET
    elif budget < MIN_THINKING_BUDGET:
        logger.warning(
            "Anthropic manual thinking: budget_tokens %d is below the API "
            "minimum; raising it to %d.",
            budget,
            MIN_THINKING_BUDGET,
        )
        budget = MIN_THINKING_BUDGET
    # Written back unconditionally so the wire value is a real int: ``"8000"``
    # and ``8000.0`` are both perfectly clear intentions and both a type error
    # on the API, so they are honoured as 8000 rather than thrown away.
    thinking["budget_tokens"] = budget

    if int(body.get("max_tokens") or 0) <= budget:
        body["max_tokens"] = budget + max(visible_tokens, 1)


def effort_capable_models(payload: dict) -> set[str]:
    """Ids from ``GET /v1/models`` that advertise an ``effort`` ladder.

    This is the live signal that decides adaptive vs manual thinking, and it is
    thrown away by :meth:`AnthropicAdapter.parse_models`, which returns bare ids.
    Exposed separately so the integration layer can keep it and hand a manual
    config back through ``extra_body`` for a model that lacks the ladder. Nothing
    calls it yet — Mytheca sends adaptive to everything.

    Reads the listing through :func:`_model_items`, the same way
    :meth:`AnthropicAdapter.parse_models` does. It used to read ``data`` alone,
    which is not a harmless narrowing: on a ``models``-keyed payload it returns
    an EMPTY set, an empty set means "no model advertises the ladder", and that
    routes every model to manual thinking — a 400 on 4.7+. A disagreement about
    where the models live would present as a healthy account with a dead
    provider, so there is one answer and both callers use it.
    """
    ids: set[str] = set()
    for model in _model_items(payload):
        if not isinstance(model, dict) or not model.get("id"):
            continue
        caps = model.get("capabilities")
        effort = caps.get("effort") if isinstance(caps, dict) else None
        if isinstance(effort, dict) and effort.get("supported"):
            ids.add(str(model["id"]))
    return ids


def _model_items(payload: object) -> list:
    """The array of model objects in a ``/v1/models`` payload.

    The reference names neither array key, so ``data`` and ``models`` are both
    accepted, first one wins, and a bare list is taken as-is. One function
    because two readers of the same listing that disagree about where the models
    are is a bug that looks like an account problem — see
    :func:`effort_capable_models`.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "models"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _budget_tokens(value: object) -> int | None:
    """A caller's ``budget_tokens`` as an int, or ``None`` if it cannot be one.

    Deliberately more forgiving than :func:`_count`, which reads *reported* usage
    and is strict on purpose: there, a ``"20"`` is a payload this adapter does
    not understand, and coercing it would launder a parse failure into a
    statistic shown to the player. Here the value came from a CALLER who wrote it
    on purpose, and ``8000.0`` (a JSON round-trip) or ``"8000"`` (an env var, a
    form field) are unambiguous intentions. The strict read turned both into
    ``None`` → ``0`` → the 1024 floor, so a 10k deliberation was quietly
    downgraded to the minimum with nothing logged and no wrong number to notice.

    A non-integral float is rejected rather than truncated: ``8000.5`` is a
    number nobody meant to type, and the caller is better told than guessed at.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value >= 0 else None
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            return None
        return parsed if parsed >= 0 else None
    return None


def _count(value: object) -> int | None:
    """A non-negative token count, or ``None`` for anything else.

    ``bool`` is excluded explicitly: it is an ``int`` in Python, and a stray
    ``True`` would report as one token rather than as missing data.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


# ---- Thinking blocks are NOT round-tripped, and that is a live limitation ---
#
# The reference is unambiguous: every ``thinking`` and ``redacted_thinking``
# block from the most recent assistant turn must be sent back **unmodified and
# in original order** on the next request. Reordering, filtering or editing any
# of them — including an apparently empty one — is a 400, and it bites hardest
# inside a tool loop, where reconstructing the assistant turn from its extracted
# text is the obvious thing to do.
#
# Mytheca does exactly that, and cannot do otherwise at this seam:
# ``ChatRequest.messages`` is typed ``list[dict[str, str]]``, so an assistant
# turn is a plain string before the adapter ever sees it. The block structure —
# and with it the ``signature`` that proves the thinking was not tampered with —
# is already gone. This adapter has nothing to replay and does not pretend to.
#
# The failure mode is specific and nasty: with thinking enabled, turn ONE
# succeeds. Turn two — the first request whose history contains an assistant
# reply that had thinking in it — is a 400. It cannot be reproduced by a
# single-turn test, and in this app "turn two" means the second beat of a live
# scene. Carrying blocks end to end means widening the message type to hold
# provider-native content; until then, treat multi-turn thinking on Anthropic as
# unsupported rather than as working-but-untested.
