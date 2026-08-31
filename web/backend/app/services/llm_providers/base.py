"""The provider seam.

Mytheca talked to exactly one OpenAI-compatible chat-completions endpoint. The
`provider` field existed in the settings row, the read schema and the Options
About tab — and was dispatched on **nowhere**, so setting it to `anthropic`
changed nothing. `core/config.py` still said the provider-agnostic interface
"lands in a later phase". This is that phase, and it makes the field that
already exists load-bearing rather than adding a parallel one beside it.

An adapter owns the five things that actually differ between backends. Every one
of them fails SILENTLY when it is wrong, which is why they are enumerated here
rather than discovered per call site:

1. **Where the request goes and how it authenticates.** Anthropic wants
   `x-api-key` plus `anthropic-version`, not `Authorization: Bearer`. Gemini
   puts the model in the path and the key in a header of its own.
2. **The body shape.** Anthropic hoists `system` out of `messages` and *requires*
   `max_tokens`; it has no `frequency_penalty`/`presence_penalty` at all. Gemini
   renames the whole envelope to `contents`/`generationConfig`.
3. **How a reply is read.** Reasoning arrives as `reasoning_content` (llama.cpp),
   `reasoning` (vLLM), a `thinking` content block (Anthropic) or a part flagged
   `thought` (Gemini). Read the wrong key and the channel is silently empty.
4. **How usage is counted.** OpenAI says `prompt_tokens` and
   `prompt_tokens_details.cached_tokens`; Anthropic says `input_tokens` and
   `cache_read_input_tokens`. Read the wrong one and the player-facing context
   dial goes blank with no error anywhere.
5. **How models are listed.** `/models` with `data[].id`, `/v1beta/models` with
   `models[].name`, or `/api/tags` with `models[].name`. Get it wrong and the
   picker is empty for a perfectly healthy endpoint.

The rule the rest of the codebase depends on: **application code never branches
on provider name.** The moment a feature file contains `if provider ==`, adding
the fifth backend becomes a refactor instead of a config line.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.schemas.reasoning import ReasoningEffort
from app.schemas.settings import LlmParams


@dataclass(frozen=True)
class ChatRequest:
    """A provider-neutral chat call, before any dialect is applied."""

    model: str
    messages: list[dict[str, str]]
    params: LlmParams
    reasoning: ReasoningEffort | None = None
    stop: list[str] | None = None
    stream: bool = False
    #: Opaque per-provider passthrough, keyed by the caller. Escape hatch only.
    extra_body: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ChatReply:
    """What every provider's reply is normalised to."""

    text: str
    #: The hidden channel, when the provider exposes one and it was requested.
    reasoning: str = ""
    #: Prompt tokens, or None when the provider did not report them.
    prompt_tokens: int | None = None
    #: Prompt tokens served from a cache, or None when not reported.
    cached_tokens: int | None = None
    #: Why generation stopped, in the PROVIDER'S OWN vocabulary — `length`
    #: (OpenAI), `max_tokens` (Anthropic), `MAX_TOKENS` (Gemini), `length`
    #: (Ollama). Not translated here: an adapter reports what the provider said,
    #: and a caller that needs to compare does so against the set of spellings
    #: rather than against one blessed word.
    #:
    #: Carried only to diagnose an EMPTY completion. "Hit the token limit" and
    #: "spent the whole budget thinking and never answered" are different
    #: problems with different fixes, and without this both reach the player as
    #: "the model returned an empty response".
    finish_reason: str | None = None
    #: The untouched provider payload. Always present, so a capability this
    #: abstraction does not cover is reachable without widening it.
    raw: dict = field(default_factory=dict)


class ProviderAdapter(Protocol):
    """One backend's dialect. Stateless; construct once, reuse."""

    #: Stable id stored in the settings row and shown in Options.
    id: str
    #: Human label for the provider dropdown.
    label: str
    #: Whether `llm.chat_complete_stream` can actually parse this provider's
    #: stream. **All four adapters can, as of 2026-08-31**: the streaming loop
    #: reads frames through `parse_stream_line` / `stream_delta` /
    #: `stream_reasoning` / `stream_usage` / `stream_done` rather than hardcoding
    #: the OpenAI SSE dialect.
    #:
    #: The flag stays on the contract rather than being deleted with the branch
    #: it fed, because the failure it describes is silent and expensive: an
    #: unrecognised stream fails the media-type check, is added to `_NO_STREAM`,
    #: and every turn degrades to the blocking path — the whole passage arriving
    #: at once instead of typing out, with no error anywhere. A fifth adapter
    #: that cannot stream (or can only stream through an SDK) declares `False`
    #: here and the Options picker says so, instead of an operator discovering
    #: it mid-scene.
    streaming_dispatched: bool

    #: Substrings, any of which in the response `content-type` means "this is
    #: the stream I asked for". OpenAI, Anthropic and Gemini all answer
    #: `text/event-stream`; Ollama answers `application/x-ndjson`. Checking for
    #: the wrong one is indistinguishable from an endpoint that refuses to
    #: stream: the reader falls back to blocking and nothing is logged.
    stream_media_types: tuple[str, ...]

    #: Whether `stop` sequences are safe to send while a reasoning channel is on.
    #: Measured on llama.cpp: a stop sequence matches the REASONING channel too,
    #: and killed a generation mid-thought, returning empty content. That is a
    #: property of the ENGINE, not a universal truth, so it lives here.
    stop_matches_reasoning: bool

    def chat_url(self, base_url: str, model: str, *, stream: bool = False) -> str:
        """Where this call goes. `stream` matters where the METHOD is in the URL.

        Gemini is the case that forces this onto the protocol: it selects
        `:streamGenerateContent?alt=sse` in the path, not `"stream": true` in
        the body, so a caller that builds a streaming body against a
        non-streaming URL gets one JSON blob back and a stream that never
        arrives. The other three ignore it.
        """

    def headers(self, api_key: str) -> dict[str, str]: ...

    def build_body(self, request: ChatRequest) -> dict:
        """Translate a `ChatRequest` into this provider's wire format."""

    def parse_reply(self, payload: dict) -> ChatReply: ...

    def models_url(self, base_url: str) -> str: ...

    def parse_models(self, payload: dict) -> list[str]: ...

    def parse_stream_line(self, line: str) -> dict | None:
        """One raw response line -> a parsed event, or None to skip it.

        The framing, not the content: SSE `data:` prefixes and the `[DONE]`
        sentinel for the three SSE dialects, bare JSON objects for Ollama's
        NDJSON. Returning None for a line this dialect has nothing to say about
        (a blank keepalive, an SSE `event:` name line, junk) is normal and must
        never raise — a malformed frame mid-scene should cost one beat's text,
        not the turn.
        """

    def stream_delta(self, event: dict) -> str:
        """The incremental text carried by one streamed event ("" if none)."""

    def stream_reasoning(self, event: dict) -> str:
        """The private deliberation carried by one event ("" if none).

        A separate channel from `stream_delta` because the model reports it
        separately and because showing them differently is the whole point of
        streaming a turn. Folding it into the text channel prints the model's
        thinking into the scene as prose; dropping it reads as "this model does
        no reasoning" rather than "we did not read it".
        """

    def stream_usage(self, event: dict) -> tuple[int | None, int | None]:
        """`(prompt_tokens, cached_tokens)` carried by one event, or `(None, None)`.

        Each dialect puts this somewhere different and at a different moment —
        OpenAI in a trailing frame with empty `choices`, Anthropic split across
        `message_start` and `message_delta`, Gemini on every frame, Ollama only
        on the closing one. A reader that gives up on a frame before asking
        throws away the only token count a streamed turn will ever report, and
        the player-facing context dial goes blank with no error anywhere.
        """

    def stream_finish_reason(self, event: dict) -> str | None:
        """Why generation stopped, if this event says. None when it does not.

        Used only to diagnose an empty completion: "hit the token limit" and
        "spent the whole budget thinking" are different problems with different
        fixes, and without this both read as "the model returned nothing".
        """

    def stream_done(self, event: dict) -> bool:
        """Whether this event ends the stream.

        Asked AFTER the event's text, usage and finish reason have been read:
        Gemini's terminal frame carries prose, and Ollama's carries the only
        usage figures in the stream. A reader that breaks first loses both.
        """


def normalize_base(base_url: str) -> str:
    """Trim a base URL to a comparable form, or raise if it is empty."""
    from app.core.errors import APIError

    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise APIError(
            400, "bad_request", "A base URL is required (e.g. http://localhost:7070/v1)."
        )
    return base


def split_system(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
    """Hoist system messages out of the list.

    Anthropic and Gemini both take the system prompt as a top-level field rather
    than a role in the conversation.

    An earlier version of this docstring said a `system` role left in `messages`
    is "ignored, with a 200 and no error". That is wrong for Anthropic and the
    adapter authors caught it: the Messages API has no `system` role and rejects
    one with a **400**. The claim is corrected here rather than deleted, because
    a confidently wrong comment is worse than none — it would have sent the next
    reader hunting for degraded prose while the endpoint was returning an error.

    Gemini's behaviour for the same mistake is **not verified** either way; do
    not assume it matches Anthropic's.
    """
    system = "\n\n".join(
        m.get("content", "") for m in messages if m.get("role") == "system"
    ).strip()
    rest = [m for m in messages if m.get("role") != "system"]
    return system, rest
