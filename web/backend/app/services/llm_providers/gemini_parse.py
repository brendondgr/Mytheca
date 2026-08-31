"""Reading a Gemini reply — which is also how you read a Gemini stream frame.

Split out of ``gemini.py`` when that file reached the project's 800-line
ceiling, along a seam the module already had: everything here answers "what did
the model say, and did it actually say it", and nothing here builds a request or
knows a URL.

The split is worth stating, because it would be easy to undo by accident. A
Gemini stream frame is a **whole ``GenerateContentResponse``**, not a delta
object — so every function below serves the blocking path and the streaming path
at the same time, and a fix to one is automatically a fix to the other. That
property is why the streaming loop can be dialect-neutral at all.
"""

from __future__ import annotations

import logging
from typing import Any, Final

from app.core.errors import APIError

logger = logging.getLogger("mytheca.llm")


#: Finish reasons that mean the model answered. The empty string covers a frame
#: that has not finished yet, which every intermediate stream frame is.
_OK_FINISH_REASONS: Final = frozenset({"", "STOP", "MAX_TOKENS"})

#: Of the reasons that are NOT normal, the ones that mean a policy refusal rather
#: than a model failure, so the two can be worded differently for the operator.
#: ``MALFORMED_FUNCTION_CALL`` is handled separately again: a model failure, and
#: retrying it can help where retrying a block never does.
_BLOCKED_FINISH_REASONS: Final = frozenset(
    {"SAFETY", "PROHIBITED_CONTENT", "RECITATION", "BLOCKLIST", "SPII", "IMAGE_SAFETY"}
)


def _candidates(payload: Any) -> list:
    """``candidates`` when it is genuinely a list, else ``[]``.

    One reading, shared by every entry point. ``candidates`` arriving as
    something else (a dict from a proxy that "helpfully" reshaped the payload, a
    number from a broken relay) used to be a ``KeyError``/``TypeError`` in
    :func:`raise_if_blocked` and :meth:`GeminiAdapter.stream_done` while
    :func:`reply_parts` handled it — the same payload diagnosed three different
    ways depending on which door it came through.
    """
    if not isinstance(payload, dict):
        return []
    candidates = payload.get("candidates")
    return candidates if isinstance(candidates, list) else []


def _first_candidate(payload: Any) -> dict:
    """The first candidate as a dict, or ``{}``.

    ``.text``/``.parts`` in the SDK read ``candidates[0]`` only and do not
    aggregate across candidates; this mirrors that rather than inventing a
    different rule for one client.
    """
    for candidate in _candidates(payload):
        return candidate if isinstance(candidate, dict) else {}
    return {}


def _error_envelope(payload: Any) -> dict:
    """A Google/relay error object riding inside a 200 body, if there is one.

    ``{"error": {"code": 429, "message": …, "status": "RESOURCE_EXHAUSTED"}}`` is
    what a real failure looks like when something between us and Google answered
    200 anyway. It has nothing to do with safety, and reporting it as a block
    accuses Google of a refusal it did not make.
    """
    error = payload.get("error") if isinstance(payload, dict) else None
    return error if isinstance(error, dict) else {}


def _raise_for_error_envelope(error: dict) -> None:
    """Surface a 200-wrapped error, with quota called out by name.

    ``429 RESOURCE_EXHAUSTED`` covers rate limits *and spend* limits, and the
    reference is explicit that retrying a spend cap never helps, so quota is
    surfaced distinctly rather than folded into a generic upstream failure. The
    status travels as 429 for the same reason: a caller that retries on 502 must
    not treat a billing cap as a blip.
    """
    status = str(error.get("status") or "").strip().upper()
    code = error.get("code")
    message = str(error.get("message") or "").strip() or "no message"
    details = {"upstreamStatus": status, "upstreamCode": code}
    if status == "RESOURCE_EXHAUSTED" or code == 429:
        raise APIError(
            429,
            "quota_exceeded",
            f"Gemini refused the call — quota or rate limit reached: {message[:300]}",
            details,
        )
    raise APIError(
        502,
        "upstream_error",
        f"Gemini returned an error in place of a reply: {message[:300]}",
        details,
    )


def raise_if_blocked(payload: dict) -> None:
    """Turn a 200 that carries no usable candidate into a typed, catchable error.

    **This is the Gemini failure mode.** A blocked prompt neither raises nor
    returns an error status: it returns 200 with an empty ``candidates`` list and
    a ``promptFeedback.blockReason``. Read naively, ``candidates[0]`` raises
    ``IndexError`` from inside our parser, and every layer above it — the turn
    loop, the trace, the toast the player sees — reports a Mytheca bug for
    something Mytheca did not do.

    But "no candidates" is not by itself evidence of a block, and this function
    used to report one for every payload that reached it. Three cases, worded
    differently on purpose, because they send the operator to three different
    places:

    * a **block** — ``promptFeedback.blockReason``, or a blocking
      ``finishReason`` on the candidate. Thresholds default to OFF on 2.5/3.x, so
      reaching this usually means an operator opted into stricter
      ``safetySettings``: precisely when a clear message matters.
    * an **error envelope** in a 200 body — a relay's failure, or Google's own
      (quota, key, model id). Nothing to do with safety.
    * an **empty or unreadable body** — no candidates, no feedback, no error. All
      that is honestly known is that nothing came back.
    """
    if not isinstance(payload, dict):
        raise APIError(502, "upstream_error", "The model endpoint returned an unreadable reply.")

    if not _candidates(payload):
        feedback = payload.get("promptFeedback")
        feedback = feedback if isinstance(feedback, dict) else {}
        reason = str(feedback.get("blockReason") or "").strip()
        if reason:
            raise APIError(
                502,
                "content_filtered",
                f"Gemini blocked the prompt ({reason}) and returned no reply.",
                {"blockReason": reason, "safetyRatings": feedback.get("safetyRatings") or []},
            )
        error = _error_envelope(payload)
        if error:
            _raise_for_error_envelope(error)
        # Neither a block nor a stated error. Say exactly that: naming a safety
        # reason here would be a fabrication, and it is the kind that sticks —
        # an operator told their prompt was refused goes and edits the prompt.
        raise APIError(
            502,
            "upstream_error",
            "Gemini returned no usable candidates and no reason (no promptFeedback, "
            "no error). The reply was empty or in an unexpected shape.",
            {"payloadKeys": sorted(str(k) for k in payload)[:20]},
        )

    candidate = _first_candidate(payload)
    finish = str(candidate.get("finishReason") or "").strip().upper()
    if finish in _OK_FINISH_REASONS:
        return
    if finish in _BLOCKED_FINISH_REASONS:
        raise APIError(
            502,
            "content_filtered",
            f"Gemini stopped generating and withheld the reply ({finish}).",
            {"finishReason": finish, "safetyRatings": candidate.get("safetyRatings") or []},
        )
    if finish == "MALFORMED_FUNCTION_CALL":
        raise APIError(
            502,
            "upstream_error",
            "Gemini emitted a malformed function call.",
            {"finishReason": finish},
        )
    # Anything else Google finished on — OTHER, LANGUAGE, UNEXPECTED_TOOL_CALL,
    # or a value added after this was written. The reference's rule is an
    # allowlist for exactly this reason; the alternative is an empty reply and no
    # error, which is indistinguishable from "the model had nothing to say".
    raise APIError(
        502,
        "upstream_error",
        f"Gemini stopped for a reason this client does not recognise ({finish}).",
        {"finishReason": finish, "safetyRatings": candidate.get("safetyRatings") or []},
    )


def reply_parts(payload: dict) -> list[dict]:
    """The reply's ``parts``, untouched — replay these rather than rebuild them.

    Reconstructing an assistant turn from extracted text drops
    ``thoughtSignature`` (and any non-text part) on the floor, which Gemini 3
    rejects on the next call. Appending what came back, verbatim, cannot.
    """
    candidate = _first_candidate(payload)
    content = candidate.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    return [p for p in parts if isinstance(p, dict)] if isinstance(parts, list) else []


def _split_parts(payload: dict) -> tuple[str, str]:
    """Answer text and thought summaries, separated by the ``thought`` flag.

    A thought part carries ``thought: true`` and otherwise looks exactly like
    prose. Concatenate the parts blindly and the model's deliberation is printed
    into the scene as if a character had said it.
    """
    answer: list[str] = []
    thoughts: list[str] = []
    for part in reply_parts(payload):
        text = part.get("text")
        if not isinstance(text, str) or not text:
            continue
        (thoughts if part.get("thought") is True else answer).append(text)
    return "".join(answer), "".join(thoughts)


def usage(payload: dict) -> tuple[int | None, int | None]:
    """``(prompt_tokens, cached_tokens)`` from ``usageMetadata``.

    Gemini spells them ``promptTokenCount`` and ``cachedContentTokenCount`` —
    nothing like OpenAI's ``prompt_tokens`` /
    ``prompt_tokens_details.cached_tokens``. Read the OpenAI names against a
    Gemini payload and both come back ``None``, at which point the player-facing
    context dial goes blank with no error anywhere. ``None`` rather than a bogus
    zero when a figure is missing, so callers fall back to their estimate.
    Streamed chunks carry ``usageMetadata`` too; the last one seen is
    authoritative.
    """
    meta = payload.get("usageMetadata") if isinstance(payload, dict) else None
    if not isinstance(meta, dict):
        return None, None
    prompt = meta.get("promptTokenCount")
    cached = meta.get("cachedContentTokenCount")
    prompt_tokens = prompt if isinstance(prompt, int) and not isinstance(prompt, bool) else None
    if prompt_tokens is not None and prompt_tokens <= 0:
        prompt_tokens = None
    cached_tokens = cached if isinstance(cached, int) and not isinstance(cached, bool) else None
    if cached_tokens is not None and cached_tokens < 0:
        cached_tokens = None
    return prompt_tokens, cached_tokens
