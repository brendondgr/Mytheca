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

from sqlalchemy.orm import Session

from app.agents._common import (
    DEFAULT_AUTHORING_EFFORT,
    docs_block,
    extract_json,
    gen_params,
    resolve_llm,
)
from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.schemas.storyline import StorylineDraftResponse
from app.services import llm

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


def draft_storyline(
    db: Session,
    seed: str,
    docs_overview: str | None = None,
    *,
    reasoning: ReasoningEffort = DEFAULT_AUTHORING_EFFORT,
) -> StorylineDraftResponse:
    """Draft title / genre / tagline / premise from a one-sentence seed."""
    seed = (seed or "").strip()
    if not seed:
        raise APIError(400, "bad_request", "Describe the world in a sentence to draft it.")
    base_url, api_key, model, params = resolve_llm(db)
    messages = [
        {"role": "system", "content": _DRAFT_SYSTEM},
        {"role": "user", "content": f"World seed: {seed}{docs_block(docs_overview)}"},
    ]
    data = extract_json(
        llm.chat_complete(
            base_url, api_key, model, messages, gen_params(params), reasoning=reasoning
        )
    )
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
    *,
    reasoning: ReasoningEffort = DEFAULT_AUTHORING_EFFORT,
) -> str:
    """Generate the agent-facing World Primer from the seed + premise."""
    premise = (premise or "").strip()
    seed = (seed or "").strip()
    if not premise and not seed:
        raise APIError(
            400, "bad_request", "Write a premise (or a one-sentence seed) before generating a primer."
        )
    base_url, api_key, model, params = resolve_llm(db)
    parts: list[str] = []
    if seed:
        parts.append(f"One-sentence seed: {seed}")
    if premise:
        parts.append(f"Premise:\n{premise}")
    user = "\n\n".join(parts) + docs_block(docs_overview)
    messages = [
        {"role": "system", "content": _PRIMER_SYSTEM},
        {"role": "user", "content": user},
    ]
    return llm.chat_complete(
        base_url, api_key, model, messages, gen_params(params), reasoning=reasoning
    )
