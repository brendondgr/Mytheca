"""Storyline authoring agent — the agent process that *builds* a storyline.

Two creation-time operations run over the configured LLM (via the proxy in
``services.llm``; credentials/model come from the settings store):

* ``draft_storyline`` — turn a one-sentence seed into the human-facing library
  metadata (title / genre / tagline / premise).
* ``generate_world_primer`` — turn the seed + premise into the agent-facing
  **World Primer**: tight prose injected into every scene so the model can open
  cold without day-one retrieval.

No retrieval here. When the caller supplies ``docs_overview`` (inline text read
from dropped reference files in the browser) it is passed for this one call only
and never persisted or indexed — the corpus/RAG layer is a later plan.
"""

from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.schemas.settings import LlmParams
from app.schemas.storyline import StorylineDraftResponse
from app.services import llm, settings_store

# Cap on inline reference text passed to a single generation (defensive; the
# frontend also caps). Keeps the prompt bounded without any storage.
_DOCS_CAP = 8000

# Authoring produces multi-paragraph output, and reasoning models spend a large
# share of the budget on hidden reasoning tokens before the visible reply (a 26B
# reasoning model was observed burning ~1.6k tokens thinking before the JSON). The
# Options default (512, tuned for the connection test) starves them; too tight a
# floor truncates the reply mid-JSON. Floor generously per-call (>= 8k) without
# touching the operator's saved setting.
_GEN_MIN_TOKENS = 8192


def _gen_params(params: LlmParams) -> LlmParams:
    """Return params with ``max_tokens`` floored for authoring generations."""
    if params.max_tokens >= _GEN_MIN_TOKENS:
        return params
    return params.model_copy(update={"max_tokens": _GEN_MIN_TOKENS})

_DRAFT_SYSTEM = (
    "You are Velora's worldbuilding assistant. Given a one-sentence seed for an "
    "interactive-fiction world, draft its library metadata. Respond with ONLY a "
    "JSON object — no prose, no markdown, no code fences — with exactly these "
    'string keys: "title" (evocative, 1-4 words), "genre" (a short genre label, '
    "e.g. 'Maritime Intrigue'), \"tagline\" (one vivid line under ~12 words), and "
    '"premise" (2-3 paragraphs of human-facing world description separated by '
    "blank lines). Include no other keys."
)

_PRIMER_SYSTEM = (
    "You are Velora's worldbuilding assistant writing a World Primer: agent-facing "
    "runtime context injected into every scene so the model can play immediately "
    "without looking things up. Write tight prose, one to four short paragraphs. "
    "Front-load the always-true, frequently-needed facts: the setting, era, and "
    "tone in brief; the handful of proper nouns the model will hit constantly "
    "(major factions, central places, key characters) each in a sentence; and the "
    "one or two load-bearing rules that govern most scenes (how power works, what "
    "is taboo, what constrains any magic). End with a single sentence telling the "
    "agent that deeper lore — specific creatures, minor factions, distant history "
    "— should be looked up when encountered and not already understood, rather "
    "than invented. Output only the primer prose: no headings, no lists, no "
    "meta-commentary."
)


def _resolve(db: Session) -> tuple[str, str, str, LlmParams]:
    """Pull the configured endpoint, raw key, model, and params from settings.

    Raises a clear 400 when the operator has not yet configured a model so the UI
    can point the user at Options instead of surfacing a raw upstream failure.
    """
    cfg = settings_store.get_llm(db)  # model + params in clear (key is masked here)
    base_url, api_key = settings_store.resolve_llm_credentials(db, None, None)
    if not base_url:
        raise APIError(400, "bad_request", "Configure a model endpoint in Options first.")
    if not cfg.model:
        raise APIError(400, "bad_request", "Choose a model in Options first.")
    return base_url, api_key, cfg.model, cfg.params


def _docs_block(docs_overview: str | None) -> str:
    text = (docs_overview or "").strip()
    if not text:
        return ""
    return (
        "\n\nReference notes from dropped files (for grounding only — do not quote "
        f"verbatim):\n{text[:_DOCS_CAP]}"
    )


def _extract_json(raw: str) -> dict:
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
        raise APIError(
            502, "upstream_error", "The model did not return valid storyline JSON."
        ) from exc
    if not isinstance(data, dict):
        raise APIError(502, "upstream_error", "The model did not return a storyline object.")
    return data


def draft_storyline(
    db: Session, seed: str, docs_overview: str | None = None
) -> StorylineDraftResponse:
    """Draft title / genre / tagline / premise from a one-sentence seed."""
    seed = (seed or "").strip()
    if not seed:
        raise APIError(400, "bad_request", "Describe the world in a sentence to draft it.")
    base_url, api_key, model, params = _resolve(db)
    messages = [
        {"role": "system", "content": _DRAFT_SYSTEM},
        {"role": "user", "content": f"World seed: {seed}{_docs_block(docs_overview)}"},
    ]
    data = _extract_json(llm.chat_complete(base_url, api_key, model, messages, _gen_params(params)))
    return StorylineDraftResponse(
        title=str(data.get("title") or "").strip(),
        genre=str(data.get("genre") or "").strip(),
        tagline=str(data.get("tagline") or "").strip(),
        premise=str(data.get("premise") or "").strip(),
    )


def generate_world_primer(
    db: Session,
    premise: str | None,
    seed: str | None = None,
    docs_overview: str | None = None,
) -> str:
    """Generate the agent-facing World Primer from the seed + premise."""
    premise = (premise or "").strip()
    seed = (seed or "").strip()
    if not premise and not seed:
        raise APIError(
            400, "bad_request", "Write a premise (or a one-sentence seed) before generating a primer."
        )
    base_url, api_key, model, params = _resolve(db)
    parts: list[str] = []
    if seed:
        parts.append(f"One-sentence seed: {seed}")
    if premise:
        parts.append(f"Premise:\n{premise}")
    user = "\n\n".join(parts) + _docs_block(docs_overview)
    messages = [
        {"role": "system", "content": _PRIMER_SYSTEM},
        {"role": "user", "content": user},
    ]
    return llm.chat_complete(base_url, api_key, model, messages, _gen_params(params))
