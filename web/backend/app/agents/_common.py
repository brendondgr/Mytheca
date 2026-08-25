"""Shared helpers for the creation-time authoring agents (storyline, character).

Both agents resolve the configured LLM the same way, floor ``max_tokens`` for
reasoning-model headroom, fold dropped-reference-doc text into the prompt, and
tolerantly parse a JSON reply. Kept in one place so the two agents cannot drift.

No retrieval here. ``docs_overview`` is inline text read from dropped files in the
browser and passed for a single generation only — never persisted or indexed.
"""

from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.schemas.settings import LlmParams
from app.services import crud, settings_store

# Cap on inline reference text passed to a single generation (the frontend also
# caps via DOCS_CHAR_CAP); keeps the prompt bounded without any storage.
DOCS_CAP = 32000

# Backend-set thinking budget for the authoring generations (storyline / character /
# setting drafts + the world build). The user has no UI lever for this — it is fixed
# here so reasoning models don't over-think interactive authoring. Triage overrides
# this to LOW for its quick classifications. (See app/schemas/reasoning.py.)
DEFAULT_AUTHORING_EFFORT = ReasoningEffort.MEDIUM

# Authoring produces multi-paragraph / structured output, and reasoning models
# spend a large share of the budget on hidden reasoning tokens before the visible
# reply. The Options default (512, tuned for the connection test) starves them;
# too tight a floor truncates mid-JSON. Floor generously per-call without touching
# the operator's saved setting. (See the reasoning-model budget memory.)
GEN_MIN_TOKENS = 8192


def decision_timeout() -> float:
    """Read window for a structural (JSON-returning, prose-free) agent call.

    The turn's decision calls are seconds-long by nature; prose generation is not. Sharing
    one window meant a stalled planner cost the player the whole prose budget in silence.
    Resolved per call so an operator override takes effect without a restart.
    """
    from app.core.config import get_settings

    return float(get_settings().llm_decision_timeout_seconds)


def plan_timeout() -> float:
    """Read window for the whole-turn plan.

    Its own setting rather than :func:`decision_timeout` because the two calls are no longer
    the same shape: the plan runs once per turn at a full thinking budget, where a decision
    call is a snap judgement made many times.
    """
    from app.core.config import get_settings

    return float(get_settings().llm_plan_timeout_seconds)


def gen_params(params: LlmParams) -> LlmParams:
    """Return params with ``max_tokens`` floored for authoring generations."""
    if params.max_tokens >= GEN_MIN_TOKENS:
        return params
    return params.model_copy(update={"max_tokens": GEN_MIN_TOKENS})


# The resolved LLM connection: (base_url, api_key, model, params). Pre-resolve once
# on the request thread and pass it into agent calls that run on worker threads — the
# workers must not touch the request Session (see resolve_llm_or + services.concurrency).
LlmConn = tuple[str, str, str, LlmParams]


def resolve_llm(db: Session) -> LlmConn:
    """Pull the configured endpoint, raw key, model, and params from settings.

    Raises a clear 400 when the operator has not configured a model, so the UI can
    point the user at Options instead of surfacing a raw upstream failure.
    """
    cfg = settings_store.get_llm(db)  # model + params in clear (key masked here)
    base_url, api_key = settings_store.resolve_llm_credentials(db, None, None)
    if not base_url:
        raise APIError(400, "bad_request", "Configure a model endpoint in Options first.")
    if not cfg.model:
        raise APIError(400, "bad_request", "Choose a model in Options first.")
    return base_url, api_key, cfg.model, cfg.params


def resolve_llm_or(db: Session, llm: LlmConn | None) -> LlmConn:
    """Return a pre-resolved connection when given one, else resolve from ``db``.

    Lets an authoring function run on a worker thread with a connection resolved on
    the calling thread (``llm=…``, no Session access), while staying backward
    compatible when called normally (``llm=None`` → resolve here)."""
    return llm if llm is not None else resolve_llm(db)


def world_context(db: Session, storyline_id: str | None) -> str:
    """Best-effort grounding: fold the target world's primer/genre into the prompt.

    Best-effort because drafting should not hard-fail if the world cannot be
    loaded; a missing/unsaved storyline simply means an ungrounded draft. Shared by
    the character and setting authoring agents so they ground identically.
    """
    if not storyline_id:
        return ""
    try:
        sl = crud.get_storyline(db, storyline_id)
    except APIError:
        return ""
    parts = [f"World: {sl.title} ({sl.genre})."]
    if sl.world_primer:
        parts.append(f"World primer:\n{sl.world_primer}")
    elif sl.premise:
        parts.append(f"World premise:\n{sl.premise}")
    return "\n\n" + "\n\n".join(parts)


def docs_block(docs_overview: str | None) -> str:
    """Fold dropped-file reference text into a grounding block (bounded)."""
    text = (docs_overview or "").strip()
    if not text:
        return ""
    return (
        "\n\nReference notes from dropped files (for grounding only — do not quote "
        f"verbatim):\n{text[:DOCS_CAP]}"
    )


# How much retrieved body text to fold per entry into the RAG grounding block.
RAG_SNIPPET_CHARS = 600


def rag_block(db: Session, storyline_id: str | None, query: str) -> str:
    """Fold hybrid-retrieved world lore into a grounding block (bounded, best-effort).

    This is where the persisted corpus is finally *used*: the seed/query retrieves
    the most relevant existing entries (characters, settings, scenarios, lore docs)
    from the same world and grounds the draft in them — alongside the transient
    ``docs_block``. No store / nothing retrieved → empty string (drafting proceeds
    ungrounded, never hard-fails)."""
    if not storyline_id:
        return ""
    try:
        from app.rag.retriever import retrieve

        entries = retrieve(db, storyline_id, query)
    except Exception:  # pragma: no cover - defensive; retrieval never blocks authoring
        return ""
    if not entries:
        return ""
    lines = [f"- {e.name} ({e.type}): {e.body[:RAG_SNIPPET_CHARS].strip()}" for e in entries]
    block = "\n".join(lines)[:DOCS_CAP]
    return (
        "\n\nRelevant established world lore (retrieved for grounding — stay "
        f"consistent with it, do not contradict or quote verbatim):\n{block}"
    )


# Reasoning-model leakage scrub for FREEFORM prose replies (the narrator). Reasoning
# models emit their chain-of-thought and harmony-style channel control tokens inline in
# ``message.content`` (e.g. ``<|channel|>final<|message|>…``, or a stray ``<channel|>``
# before the real answer, plus ``*Check:*``/``*Revised:*`` self-checks). The marker-parsed
# agents (character emission) are immune because they extract by ``<type:>``/``<thinking>``
# tags; the narrator returns raw prose, so it needs an explicit scrub.
#
# NB: intentionally does NOT touch the app's own ``<thinking>``/``<type:>`` tags — apply
# this ONLY to freeform prose, never to marker-parsed character output.
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_CHANNEL_RE = re.compile(r"<\|?channel\|?>", re.IGNORECASE)
_HARMONY_LABEL_RE = re.compile(r"^\s*(?:final|analysis|commentary)\b[:\s]*", re.IGNORECASE)
_HARMONY_TOKEN_RE = re.compile(
    r"<\|?(?:channel|message|start|end|return|constrain|assistant|analysis|commentary|final)\|?>",
    re.IGNORECASE,
)


def strip_reasoning(text: str) -> str:
    """Strip reasoning-model chain-of-thought + channel tokens from a freeform reply.

    Keeps only the model's final answer: drop any paired ``<think>…</think>`` block,
    then — since the visible final answer always follows the last channel marker in the
    harmony format — take the text after the last ``<|channel|>``/``<channel|>`` marker
    (dropping a leading ``final``/``analysis`` label), and scrub any residual harmony
    control tokens. A clean reply with no markers is returned trimmed and unchanged.
    """
    if not text:
        return ""
    text = _THINK_BLOCK_RE.sub("", text)
    matches = list(_CHANNEL_RE.finditer(text))
    if matches:
        text = text[matches[-1].end() :]
        text = _HARMONY_LABEL_RE.sub("", text, count=1)
    text = _HARMONY_TOKEN_RE.sub("", text)
    return text.strip()


def extract_json(raw: str) -> dict:
    """Best-effort parse of a model's JSON reply (tolerant of fences/surrounds)."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise APIError(502, "upstream_error", "The model did not return valid JSON.") from exc
    if not isinstance(data, dict):
        raise APIError(502, "upstream_error", "The model did not return a JSON object.")
    return data


class InlineReasoningSplitter:
    """Split a *streaming* ``content`` channel into reasoning text and answer text.

    The fallback for endpoints that inline their chain-of-thought in ``content`` as
    ``<think>…</think>``. The endpoint Mytheca is normally pointed at does not do this —
    it returns a separate ``reasoning_content`` field, which needs no parsing at all —
    but a model that inlines its thinking would otherwise stream that thinking straight
    into the story as if it were prose.

    :func:`strip_reasoning` cannot be reused here because it operates on a finished
    string: it takes the text after the *last* channel marker, which is unknowable while
    the text is still arriving. This class makes the same split incrementally, at the
    cost of only handling the ``<think>`` form (the harmony-channel form is still scrubbed
    in one pass at the end, where the last marker IS known).

    Feed it deltas with :meth:`push`; each call returns ``(answer, reasoning)`` for *that*
    delta. A tag split across two deltas is held back until it resolves, so a partial
    ``"<thi"`` is never emitted as prose.
    """

    _OPEN = "<think>"
    _CLOSE = "</think>"

    def __init__(self) -> None:
        self._buf = ""
        self._in_think = False

    #: Harmony control tokens are dropped from the answer channel as they stream. The
    #: full :func:`strip_reasoning` pass cannot run incrementally — it keeps the text
    #: after the LAST channel marker, and which marker is last is unknowable mid-stream —
    #: but suppressing the tokens themselves stops raw control glyphs rendering as prose.
    _HARMONY = _HARMONY_TOKEN_RE

    def push(self, delta: str) -> tuple[str, str]:
        """Consume one delta; return the ``(answer, reasoning)`` text it contributed."""
        if not delta:
            return "", ""
        self._buf += delta
        answer: list[str] = []
        reasoning: list[str] = []
        while self._buf:
            if self._in_think:
                end = self._buf.lower().find(self._CLOSE)
                if end == -1:
                    safe = self._safe_len()
                    if safe:
                        reasoning.append(self._buf[:safe])
                        self._buf = self._buf[safe:]
                    break
                reasoning.append(self._buf[:end])
                self._buf = self._buf[end + len(self._CLOSE) :]
                self._in_think = False
                continue
            start = self._buf.lower().find(self._OPEN)
            if start == -1:
                safe = self._safe_len()
                if safe:
                    answer.append(self._buf[:safe])
                    self._buf = self._buf[safe:]
                break
            answer.append(self._buf[:start])
            self._buf = self._buf[start + len(self._OPEN) :]
            self._in_think = True
        return self._HARMONY.sub("", "".join(answer)), "".join(reasoning)

    def flush(self) -> tuple[str, str]:
        """Drain whatever is still held back once the stream has ended."""
        rest, self._buf = self._buf, ""
        if not rest:
            return "", ""
        return ("", rest) if self._in_think else (self._HARMONY.sub("", rest), "")

    def _safe_len(self) -> int:
        """How much of the buffer cannot still turn out to be part of a tag.

        An unterminated ``<`` is held back wholesale rather than matched against a
        specific tag: it may be the start of ``<think>``, but equally of a harmony
        control token, and either way it must not reach the reader as prose.
        """
        start = self._buf.rfind("<")
        return len(self._buf) if start == -1 or ">" in self._buf[start:] else start
