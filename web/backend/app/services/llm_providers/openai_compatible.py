"""The OpenAI-compatible dialect: ``/chat/completions``, Bearer auth, ``choices[0]``.

This adapter is a **port, not a rewrite**. It is the path every existing Mytheca
installation is already on — the local llama.cpp / vLLM / relay endpoints and the
settings row's default ``provider`` value all resolve here — so a difference
between this file and ``services/llm.py``'s ``_completion_request`` is a
regression, not an improvement. Every body key, the order they are written in,
and the ``.strip()`` on the reply were taken from that function verbatim rather
than from the OpenAI documentation, because the documentation describes hosted
OpenAI and this provider id is mostly pointed at something else.

Three responsibilities stay OUTSIDE this object, because each needs I/O or
accumulated state and an adapter is pure:

* **The thinking budget.** See :attr:`OpenAICompatibleAdapter.reasoning_applied_by_caller`.
* **The learned context-window clamp** (``llm._fit_max_tokens``). It is taught by
  an upstream 400 and cached per endpoint+model, so it is request *history*, not
  dialect.
* **The harmony / ``<think>`` scrub** (``agents._common.strip_reasoning``). That
  cleans up what a *model* leaks into ``content``, which is the same text on any
  provider serving that model.

Notes marked ``HOSTED-OPENAI:`` record where the current behaviour is wrong for
**api.openai.com specifically** while being right for the local servers this
code was built against. None of them change what is sent. They are written down
so that fixing them starts from evidence rather than from rediscovering the same
400 a third time.

**The base URL must already carry the API prefix.** Every path here is appended
to it verbatim, so the endpoint is expected to look like
``http://host:8000/v1`` and NOT ``http://host:8000`` — the second form is what
vLLM and llama.cpp print in their own startup banner, and it turns every call
into ``…/chat/completions`` against a server that serves ``/v1/chat/completions``.
That is a 404, a 404 is never retried, and nothing in the resulting message names
the cause. This is the single most common misconfiguration on this provider.
:meth:`OpenAICompatibleAdapter.chat_url` logs a warning when it sees a base with
no path at all; it does not rewrite the URL, because appending ``/v1`` would
break every gateway that legitimately serves this API at its root.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Final

from app.schemas.reasoning import ReasoningEffort
from app.schemas.settings import LlmParams
from app.services.llm_providers.base import ChatReply, ChatRequest, normalize_base

# Deliberately the same logger name ``services/llm.py`` uses. The dropped-stop
# message below is a diagnostic an operator already greps for under this name;
# moving it to a new logger would silently take it out of their filter.
logger = logging.getLogger("mytheca.llm")

#: Marker key on :data:`STREAM_DONE`. :meth:`parse_stream_line` distinguishes the SSE
#: terminator from "this line carried nothing" by object *identity* against a bare
#: ``{}``, which stops working the moment the sentinel crosses a module boundary
#: and gets copied or re-created. A marker key survives that; no provider chunk
#: carries this name.
_DONE_MARKER: Final[str] = "__mytheca_stream_done__"

#: Returned by :meth:`OpenAICompatibleAdapter.parse_stream_line` for ``data: [DONE]``.
STREAM_DONE: Final[dict[str, Any]] = {_DONE_MARKER: True}

#: Field names carrying a model's deliberation, in the order they are checked.
#:
#: Both spellings are live and the difference is not cosmetic: reading only one
#: silently discards the whole channel on any endpoint using the other, which
#: then reads as "this model does no reasoning" rather than "we did not look".
#:  * ``reasoning_content`` — llama.cpp.
#:  * ``reasoning``         — vLLM (observed on qwen38-27B-awq behind the relay).
#:
#: HOSTED-OPENAI: neither is ever populated. Chat Completions returns no reasoning
#: TEXT at all — only a count, at ``usage.completion_tokens_details.reasoning_tokens``.
#: The consequence is downstream: ``llm._raise_empty_completion`` picks its
#: diagnosis by whether reasoning text arrived, so an OpenAI reasoning model that
#: burns its whole allowance thinking is reported as "hit its token limit" rather
#: than "spent its whole budget thinking". Same root cause, different advice.
_REASONING_FIELDS: Final[tuple[str, ...]] = ("reasoning_content", "reasoning")

#: Base URLs already warned about by :meth:`OpenAICompatibleAdapter._warn_if_pathless`,
#: so a misconfigured endpoint is reported once rather than once per request.
#: Module-level rather than instance state because the adapter is constructed once
#: and shared: this is a log de-duplicator, and no answer this object returns
#: depends on it.
_WARNED_PATHLESS_BASES: set[str] = set()


class OpenAICompatibleAdapter:
    """The dialect spoken by OpenAI, vLLM, llama.cpp, Ollama's ``/v1`` and relays."""

    id: str = "openai-compatible"
    label: str = "OpenAI-compatible"

    #: READ THE NAME, NOT ``base.py``'s FIRST LINE. This flag means "on this engine a
    #: ``stop`` sequence is matched against the REASONING channel as well as the
    #: answer" — so ``True`` means a stop sequence is **unsafe** while reasoning is
    #: on, which is exactly how :meth:`_stop_is_safe` treats it and how the
    #: ``llm.stop_is_safe`` constant it was lifted from behaved.
    #:
    #: ``base.py`` opens its declaration with "Whether `stop` sequences are safe to
    #: send while a reasoning channel is on", which states the INVERSE, and then
    #: immediately describes the llama.cpp measurement under which ``True`` can only
    #: mean unsafe. That first line is a mis-worded doc, not a second meaning: every
    #: adapter in this package sets the value the way the name reads, and the
    #: contract test pins ``openai-compatible`` at ``True`` while Anthropic and
    #: Gemini — the two backends where a stop sequence provably cannot touch a
    #: server-side reasoning channel — are ``False``. Do NOT "reconcile" the two by
    #: flipping the value here; that would send stop sequences into exactly the
    #: generation this measurement killed. The wording in ``base.py`` is what needs
    #: fixing, and that file is edited elsewhere.
    #:
    #: Measured on the deployed llama.cpp route: ``stop: ["<END_SCENARIO>"]`` killed
    #: a generation mid-*thought* and returned empty ``content``, because the stop
    #: sequence is matched against the reasoning channel too. It was a global
    #: constant in ``llm.stop_is_safe``; it becomes this provider's property here,
    #: since it is a property of the engine rather than a truth about all backends.
    #:
    #: HOSTED-OPENAI: over-conservative. Reasoning there is server-side and never
    #: enters the sampled stream a stop sequence can match. The cost of the extra
    #: caution is an unbounded generation, never an error, so it stays True until
    #: someone measures a hosted endpoint rather than assuming one.
    streaming_dispatched: bool = True

    stream_media_types: tuple[str, ...] = ("event-stream",)

    stop_matches_reasoning: bool = True

    #: The thinking budget is NOT written by :meth:`build_body`, and that omission
    #: is the contract. This family carries the budget under a key chosen by the
    #: *engine* behind the endpoint — ``thinking_token_budget`` (vLLM) or
    #: ``thinking_budget_tokens`` (llama.cpp), both when the engine is a relay or
    #: unknown — and picking between them requires probing ``/v1/models`` and
    #: ``/props``, which is I/O this object must not perform.
    #:
    #: So the caller keeps doing exactly what ``llm._completion_request`` does
    #: today: after ``build_body``, when ``reasoning is not None``, call
    #: ``llm_backend.get_backend(base_url, api_key)`` and
    #: ``llm_backend.apply_reasoning(body, backend, reasoning)``. Dropping that
    #: call raises nothing and returns a 200 — a reasoning model simply thinks
    #: without a ceiling and the turn gets slower, which is why it is flagged here
    #: rather than left to be inferred from a missing key.
    #:
    #: HOSTED-OPENAI: both keys are meaningless there. The hosted equivalent is a
    #: flat ``reasoning_effort: "low"|"medium"|"high"`` string on Chat Completions
    #: (nested as ``reasoning: {"effort": ...}`` on the Responses API), i.e. an
    #: enum rather than a token count, so ``THINKING_BUDGET`` does not translate —
    #: it would have to be bucketed. Whether OpenAI *rejects* the unrecognised keys
    #: or ignores them is NOT VERIFIED here; the reference only documents that the
    #: Python SDK raises on unknown top-level kwargs, which says nothing about a
    #: raw POST.
    reasoning_applied_by_caller: bool = True

    # ---- Routing ------------------------------------------------------------

    def chat_url(self, base_url: str, model: str, *, stream: bool = False) -> str:
        """``{base}/chat/completions`` — the base must ALREADY end in ``/v1``.

        ``model`` and ``stream`` are accepted and unused: this dialect names the
        model in the body and asks for a stream with ``"stream": true``. Gemini
        puts both in the URL, which is why the signature carries them.

        Nothing here supplies a missing ``/v1``; see :meth:`_warn_if_pathless` for
        why a bare ``http://host:8000`` is only warned about and not repaired.
        """
        base = normalize_base(base_url)
        self._warn_if_pathless(base)
        return f"{base}/chat/completions"

    def models_url(self, base_url: str) -> str:
        """``{base}/models`` — same base-URL rule as :meth:`chat_url`.

        Discovery is usually where a missing ``/v1`` is first *seen*: the model
        picker comes back empty, which reads as "this endpoint has no models"
        rather than "we asked the wrong path". The warning is emitted from
        ``chat_url`` only, so that one misconfigured endpoint produces one line
        instead of two.
        """
        return f"{normalize_base(base_url)}/models"

    def _warn_if_pathless(self, base: str) -> None:
        """Log once when a base URL looks like it is missing its ``/v1`` prefix.

        Only a base with NO path at all is flagged — ``http://host:8000``, the
        form the local servers print at startup. A base that carries some other
        path is very often correct (``https://gateway/openai/v1``, an Azure
        deployment path, a reverse proxy that strips the prefix), so demanding a
        literal ``/v1`` suffix would cry wolf on working installs, and this warning
        is only worth anything if it is never wrong.

        Detection only. Rewriting the URL would change what a *correct*
        root-mounted endpoint is sent, which is the one thing this port may not do
        — and it would hide the mistake instead of naming it.
        """
        tail = base.split("://", 1)[-1]
        if "/" in tail or base in _WARNED_PATHLESS_BASES:
            return
        _WARNED_PATHLESS_BASES.add(base)
        logger.warning(
            "LLM base URL %s has no path. This dialect appends /chat/completions to the "
            "base, so a server that serves /v1/chat/completions will 404 every call "
            "(and a 404 is not retried). Did you mean %s/v1 ?",
            base,
            base,
        )

    def headers(self, api_key: str) -> dict[str, str]:
        """Content-Type, plus ``Authorization: Bearer`` only when a key is set.

        The header is conditional because vLLM and llama.cpp ship with no auth
        unless launched with ``--api-key``, and Mytheca talks to them over raw
        httpx. (The ``openai`` SDK refuses to construct with a falsy key and
        forces a ``"not-needed"`` placeholder; that constraint does not apply
        here, so an empty key means an absent header rather than a fake one.)
        """
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    # ---- Request ------------------------------------------------------------

    def build_body(self, request: ChatRequest) -> dict:
        """Port of ``llm._completion_request``'s body. Key order is load-bearing.

        Not the insertion order of a JSON object — the *sequence of writes*. The
        ``extra_body`` merge lands before ``stop``, so a caller's ``extra_body``
        stop is overridden by the request's; and the streaming keys land last, so
        ``extra_body`` cannot turn streaming off underneath the streaming path.
        Reordering these is a silent behaviour change, which is why they are not
        collapsed into one literal.
        """
        if not request.model:
            # Kept here rather than left to the endpoint: without it a missing
            # model is an upstream 400 rendered as a bare "the model endpoint
            # returned 400", which sends the operator to the server logs for a
            # config mistake this side already knows about.
            from app.core.errors import APIError

            raise APIError(400, "bad_request", "A model is required to generate.")

        params = request.params or LlmParams()
        body: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
            "top_p": params.top_p,
            "frequency_penalty": params.frequency_penalty,
            "presence_penalty": params.presence_penalty,
        }
        # HOSTED-OPENAI: this block is a hard 400 on any reasoning model there
        # (ids matching ``o[1-9]`` or ``gpt-5``). Those models REJECT rather than
        # ignore ``temperature``, ``top_p``, ``frequency_penalty`` and
        # ``presence_penalty``, and rename ``max_tokens`` to
        # ``max_completion_tokens``. Local engines accept all five from every
        # model, which is why nothing has ever noticed. Fixing it needs an
        # id-pattern heuristic (a whitelist goes stale in weeks), so it is a
        # decision, not a tidy-up, and it is not made here.

        # The escape hatch for vLLM guided/structured decoding
        # (``guided_json`` / ``guided_choice``) and llama.cpp's ``grammar``.
        # Merged wholesale and unvalidated by design: the point of the hatch is
        # to reach a capability this abstraction does not model.
        if request.extra_body:
            body.update(request.extra_body)

        if request.stop:
            if self._stop_is_safe(request.reasoning):
                body["stop"] = list(request.stop)
            else:
                # Dropped rather than raised. A caller asking for a stop sequence
                # wants a bounded generation, and refusing the whole call is a
                # worse answer than generating without the bound.
                #
                # WARNING, not DEBUG. This is the request the caller asked for and
                # did not get; at DEBUG the line sits below the root logger's
                # default level, so the previous claim that it was "logged so the
                # difference is not invisible" was simply false — nothing reached
                # an operator unless they had already gone looking. It cannot
                # flood: it needs a caller that sets `stop` AND leaves reasoning
                # on, and no agent in the tree passes `stop` today.
                logger.warning(
                    "stop sequence dropped: reasoning channel is on (%s)", request.reasoning
                )

        if request.stream:
            body["stream"] = True
            # Without this, streaming returns NO usage at all — the single most
            # common cause of "token accounting is zero, but only when streaming".
            # It is what fills the story player's context dial on a streamed turn.
            # Local servers vary in honouring it and none of them document it;
            # a missing usage frame degrades to ``prompt_tokens=None`` and an
            # estimate, so an endpoint that ignores it costs accuracy, not a turn.
            body["stream_options"] = {"include_usage": True}
        # No ``"stream": False`` on the blocking path: the current code omits the
        # key entirely there, and an added key is a changed request body.

        return body

    def _stop_is_safe(self, reasoning: ReasoningEffort | None) -> bool:
        """Whether ``stop`` may ride along at this effort. Port of ``llm.stop_is_safe``.

        Note the polarity of the flag it reads:
        :attr:`stop_matches_reasoning` ``True`` means stop is UNSAFE with reasoning
        on (see the long note there about ``base.py``'s inverted wording), which is
        why the early return is ``not self.stop_matches_reasoning``.

        Only an explicit :attr:`ReasoningEffort.NONE` counts as "the channel is
        off". ``None`` is not off — it sends no budget key at all, so the server's
        own default applies (``--reasoning-budget -1`` on the local endpoint:
        unlimited), and treating it as off is how a tag ends up killing a
        generation mid-thought.
        """
        if not self.stop_matches_reasoning:
            return True
        return reasoning is ReasoningEffort.NONE

    # ---- Reply --------------------------------------------------------------

    def parse_reply(self, payload: dict) -> ChatReply:
        """Read one completion. A malformed payload yields an EMPTY reply, never a raise.

        A well-formed payload takes byte-for-byte the path it took before: the
        guards below only decide what happens to shapes that used to throw.

        These reads used to be unguarded, on the stated grounds that the caller
        wrapped them in ``except (ValueError, AttributeError, IndexError,
        TypeError)``. No caller uses that tuple with this method. The only caller
        of ``parse_reply`` today is ``llm.test_chat``, which catches ``(ValueError,
        AttributeError, IndexError, KeyError)`` — no ``TypeError``; the generation
        path inlines its own copy of this parse in ``llm._completion_request`` and
        catches the tuple *with* ``TypeError`` but *without* ``KeyError``. Neither
        set covers both holes, and each hole was reachable:

        * ``{"choices": {"a": 1}}`` → a dict is truthy, so ``choices[0]`` is a key
          lookup → ``KeyError`` (escapes the generation path).
        * ``{"choices": 5}`` → ``TypeError``, which escaped ``test_chat`` and 500'd
          ``POST /api/options/llm/test``.

        A 500 on the connection test is the worst available answer: it is the one
        page whose whole job is to explain what is wrong with an endpoint.

        What the guards cost is worth stating plainly, because the old comment
        claimed the opposite. Junk now parses as an empty reply, so the connection
        test reports **success with a blank sample** rather than an error — which
        it already did for every junk shape it happened to catch, so this makes the
        behaviour consistent rather than introducing it. Telling "the endpoint sent
        nonsense" apart from "the model had nothing to say" is not something this
        method can do (an empty ``content`` with valid framing is a normal, common
        reply), so an accurate diagnosis has to come from the caller comparing the
        reply against ``ChatReply.raw`` — which is why ``raw`` is carried.

        The usage figures are guarded for a different reason: a *missing* usage
        block is normal rather than malformed.
        """
        payload = payload if isinstance(payload, dict) else {}
        choices = payload.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices else {}
        message = choice.get("message") if isinstance(choice, dict) else None
        message = message if isinstance(message, dict) else {}
        content = message.get("content")
        # ``isinstance`` rather than ``or ""``: a non-string ``content`` (a gateway
        # echoing Responses-style content *parts*, say) used to raise AttributeError
        # on ``.strip()``. Reading it as empty is the same outcome the rest of these
        # guards produce; assembling text out of parts would be a new feature, not a
        # fix, and is deliberately not attempted here.
        text = content.strip() if isinstance(content, str) else ""
        if not text:
            self._note_refusal(message)
        return ChatReply(
            text=text,
            reasoning=self.reasoning_text(message),
            prompt_tokens=self.prompt_tokens(payload),
            cached_tokens=self.cached_tokens(payload),
            finish_reason=self.stream_finish_reason(payload),
            raw=payload,
        )

    def _note_refusal(self, message: dict) -> None:
        """Log a hosted refusal, which otherwise reads as "the model said nothing".

        HOSTED-OPENAI: Chat Completions signals a refused generation *without* an
        error — the reference is explicit that "Refusals surface as
        ``message.refusal`` (Chat Completions)", alongside ``content: null``, at
        HTTP 200. Nothing in this adapter read that key, so a refusal arrived
        downstream as ``text == ""`` and was diagnosed by
        ``llm._raise_empty_completion`` as "The model returned an empty response",
        sending the operator to hunt a broken endpoint instead of a refused prompt.
        (``finish_reason: "content_filter"`` is the related signal for a *filtered*
        completion; :meth:`finish_reason` already surfaces that one to the caller.)

        Logged rather than returned, because putting it anywhere in
        :class:`ChatReply` means either handing a refusal string to the emission
        parser as if it were prose (``text``) or widening ``base.py``, which is a
        shared file this port does not own. WARNING, not DEBUG: it is the only
        trace of the real cause, and it is unreachable on the local engines this
        provider is usually pointed at, which never set the key.
        """
        refusal = message.get("refusal")
        if isinstance(refusal, str) and refusal.strip():
            logger.warning(
                "model refused the request (message.refusal): %s", refusal.strip()[:200]
            )

    def reasoning_text(self, payload: dict) -> str:
        """The deliberation from a message OR a streaming delta, either spelling.

        One method for both because the two shapes carry the field identically —
        which is exactly why reading it in only one of the two paths is such an
        easy mistake.
        """
        if not isinstance(payload, dict):
            return ""
        for name in _REASONING_FIELDS:
            value = payload.get(name)
            if value:
                return str(value)
        return ""

    def prompt_tokens(self, payload: dict) -> int | None:
        """``usage.prompt_tokens``, or ``None`` when absent or not a positive int.

        ``None`` rather than 0: callers fall back to a character-count estimate,
        and a bogus zero would render as "this turn used no context" on the dial.
        """
        usage = payload.get("usage") if isinstance(payload, dict) else None
        value = usage.get("prompt_tokens") if isinstance(usage, dict) else None
        # ``bool`` is an ``int`` subclass; ``True`` would otherwise count as 1 token.
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value if value > 0 else None

    def cached_tokens(self, payload: dict) -> int | None:
        """``usage.prompt_tokens_details.cached_tokens`` — the prefix-cache hit.

        The only honest measure of whether the prompt is laid out so history can
        be reused between turns. Without it a cache regression is completely
        silent: latency just creeps up as the scene gets longer. Many endpoints
        omit ``prompt_tokens_details`` entirely, hence ``None``.

        HOSTED-OPENAI: this spelling is correct there too (it is Anthropic that
        says ``cache_read_input_tokens``). What is missing is ``prompt_cache_key``
        in the request — on newer hosted models that key is what routes a shared
        prefix to a cache-warm backend, and Mytheca's whole prompt layout is built
        around prefix reuse, so it is the one hosted gap that would actually cost
        money rather than correctness.
        """
        usage = payload.get("usage") if isinstance(payload, dict) else None
        details = usage.get("prompt_tokens_details") if isinstance(usage, dict) else None
        value = details.get("cached_tokens") if isinstance(details, dict) else None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return value

    def finish_reason(self, payload: dict) -> str | None:
        """``choices[0].finish_reason`` from a completion or a streamed chunk.

        Beyond the ``ProviderAdapter`` protocol, which has nowhere to put it:
        ``ChatReply`` carries no such field. It is needed anyway, because telling
        "the model hit its token limit" apart from "the model returned nothing"
        is the difference between a useful error and a shrug.
        """
        if not isinstance(payload, dict):
            return None
        choices = payload.get("choices") or []
        choice = choices[0] if choices else {}
        reason = choice.get("finish_reason") if isinstance(choice, dict) else None
        return str(reason) if reason else None

    # ---- Models -------------------------------------------------------------

    def parse_models(self, payload: dict) -> list[str]:
        """``{"data": [{"id": ...}]}`` — plus the shapes real servers actually send.

        The bare-list and bare-string fallbacks are not defensive padding: they
        are in the shipped behaviour because endpoints in this family have
        returned both, and an over-strict parse shows an empty picker for a
        perfectly healthy server.

        HOSTED-OPENAI: this listing mixes chat, embedding, audio, image and
        moderation models with nothing to tell them apart, and reports no context
        window or capability flags. The picker therefore offers dozens of ids that
        cannot serve a turn. It has never mattered because vLLM and llama.cpp
        serve exactly one model each.

        A blank entry is dropped in BOTH shapes. ``{"id": ""}`` was already
        filtered; a bare ``""`` was not, because ``isinstance(m, str)`` is true of
        the empty string — so a listing containing one put an empty row in the
        model picker, and picking it writes an empty ``model`` into the settings
        row, whose next generation is the "A model is required to generate." raise
        in :meth:`build_body`. Inherited from ``llm.py``'s filter; the two shapes
        were meant to be equivalent, and now are.
        """
        data = payload.get("data") if isinstance(payload, dict) else None
        items = data if isinstance(data, list) else (payload if isinstance(payload, list) else [])
        return [
            str(m.get("id")) if isinstance(m, dict) else str(m)
            for m in items
            if (isinstance(m, dict) and m.get("id")) or (isinstance(m, str) and m.strip())
        ]

    # ---- Streaming ----------------------------------------------------------

    def parse_stream_line(self, line: str) -> dict | None:
        """One SSE line → its JSON payload, :data:`STREAM_DONE`, or ``None`` to skip.

        Beyond the protocol, which starts at an already-parsed event. Framing is
        dialect: this family sends ``data: {json}`` and terminates with the
        non-JSON literal ``data: [DONE]``, where Anthropic sends typed ``event:``
        lines and Gemini a JSON array. ``None`` covers blank keep-alive lines,
        comments, and any chunk that is not a JSON object — none of which are
        errors.
        """
        line = (line or "").strip()
        if not line or not line.startswith("data:"):
            return None
        data = line[len("data:") :].strip()
        if data == "[DONE]":
            return STREAM_DONE
        try:
            parsed = json.loads(data)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def stream_delta(self, event: dict) -> str:
        """``choices[0].delta.content`` for one chunk, ``""`` when it carries none.

        Read the usage off the chunk BEFORE deciding a chunk is uninteresting:
        the final usage frame arrives with ``choices: []``, so any loop that
        skips empty-choices chunks first throws away the only token count the
        streamed call will ever report.
        """
        if not isinstance(event, dict):
            return ""
        choices = event.get("choices") or []
        choice = choices[0] if choices else {}
        delta = (choice.get("delta") or {}) if isinstance(choice, dict) else {}
        content = delta.get("content") if isinstance(delta, dict) else None
        return str(content) if content else ""

    def stream_reasoning(self, event: dict) -> str:
        """The deliberation carried by one chunk, ``""`` when it carries none.

        Beyond the protocol, which models a stream as text only. Without it the
        thinking channel is lost on every streamed turn — and lost invisibly,
        which is the failure this seam exists to prevent.
        """
        if not isinstance(event, dict):
            return ""
        choices = event.get("choices") or []
        choice = choices[0] if choices else {}
        delta = (choice.get("delta") or {}) if isinstance(choice, dict) else {}
        return self.reasoning_text(delta)

    def stream_done(self, event: dict) -> bool:
        """True only for the terminator produced by :meth:`parse_stream_line`.

        Not ``finish_reason`` — the usage frame arrives AFTER it, and ending the
        loop on it blanks the token count for every streamed turn. And not "the
        chunk is empty" either: a literal ``data: {}`` is a chunk with nothing in
        it, which this dialect answers by skipping, not by stopping.
        """
        return isinstance(event, dict) and event.get(_DONE_MARKER) is True

    def stream_usage(self, event: dict) -> tuple[int | None, int | None]:
        """The token counts on a streamed frame — the same shape as a reply's.

        The usage frame arrives LAST and carries ``choices: []``, which is why
        this is asked of every frame rather than only of ones with content.
        It is present at all only because :meth:`build_body` sends
        ``stream_options: {"include_usage": true}``.
        """
        if not isinstance(event, dict):
            return None, None
        return self.prompt_tokens(event), self.cached_tokens(event)

    def stream_finish_reason(self, event: dict) -> str | None:
        """``choices[0].finish_reason``, once the endpoint sets it."""
        if not isinstance(event, dict):
            return None
        choices = event.get("choices") or []
        choice = choices[0] if choices else {}
        reason = choice.get("finish_reason") if isinstance(choice, dict) else None
        return str(reason) if reason else None
