"""Entity-extraction agent — split one reference document into its subjects.

A single creation-time operation over the configured LLM (same proxy + settings
resolution as the other authoring agents, via ``agents._common``):

* ``extract_entities`` — read ONE reference document and return every distinct
  **character** and every distinct **setting/place** it describes, each as a
  focused per-subject brief a downstream draft agent can flesh out.

This is what lets **Build the whole world** stop losing people: a markdown file
naming several characters becomes several extracted character briefs (one card
each), instead of collapsing into a single card or vanishing into ``other``-bucket
lore. A single-subject doc yields one entity; a pure lore/history doc (no
profile-worthy subject) yields none — it still grounds the world elsewhere.

Nothing is persisted here; the build orchestrator drafts a card per returned
entity. No graph, no retrieval.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents._common import (
    DEFAULT_AUTHORING_EFFORT,
    DOCS_CAP,
    extract_json,
    gen_params,
    resolve_llm,
)
from app.schemas.build import ExtractedEntities, ExtractedEntity
from app.services import llm

# Per-subject source brief is bounded so a multi-entity doc can't blow the prompt
# budget of the downstream draft calls.
_SOURCE_CAP = 4000

_EXTRACT_SYSTEM = (
    "You are Velora's entity-extraction assistant for an interactive-fiction world. "
    "You are given ONE reference document. Identify every DISTINCT character and "
    "every DISTINCT setting (place/location) the document describes well enough to "
    "build a profile for. Respond with ONLY a JSON object — no prose, no markdown, "
    "no code fences — of the form "
    '{"characters": [{"name": "<subject name>", "source": "<a self-contained '
    "paragraph describing ONLY this one character, drawn from the document: who "
    'they are, role, appearance, personality, goals>"}], "settings": [{"name": '
    '"<place name>", "source": "<a self-contained paragraph describing ONLY this '
    'one place>"}]}.\n'
    "Rules:\n"
    "- One entry per distinct subject. If the document describes five characters, "
    "return five character entries; if it describes one, return one.\n"
    "- 'source' must be focused on that single subject only (do not mix subjects) "
    "and must stand alone — a later agent fleshes out the card from it without "
    "seeing the original document.\n"
    "- Include a subject only if the document gives enough to characterise it. If "
    "the document is general lore, history, rules, or a timeline with no "
    "profile-worthy character or place, return empty lists.\n"
    "- Do NOT invent subjects that are not in the document."
)


def _coerce_entities(rows: object) -> list[ExtractedEntity]:
    """Turn a model list-of-rows into clean ExtractedEntity values (named only)."""
    out: list[ExtractedEntity] = []
    seen: set[str] = set()
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:  # de-dup within a single doc
            continue
        seen.add(key)
        source = str(row.get("source") or "").strip()[:_SOURCE_CAP] or name
        out.append(ExtractedEntity(name=name, source=source))
    return out


def extract_entities(
    db: Session,
    doc_text: str,
    grounding: str | None = None,
    *,
    doc_name: str = "",
) -> ExtractedEntities:
    """Extract the distinct characters + settings described in one document.

    Best-effort by design at the orchestration layer (the build wraps the call), but
    a malformed JSON reply still raises through ``extract_json`` so a flat failure is
    visible. Blank input short-circuits to empty lists (no LLM call).
    """
    text = (doc_text or "").strip()
    if not text:
        return ExtractedEntities()

    base_url, api_key, model, params = resolve_llm(db)
    header = f"Document name: {doc_name}\n\n" if doc_name else ""
    ground = f"\n\nWorld context (for consistency only):\n{grounding.strip()}" if grounding else ""
    user = f"{header}Document content:\n{text[:DOCS_CAP]}{ground}"
    messages = [
        {"role": "system", "content": _EXTRACT_SYSTEM},
        {"role": "user", "content": user},
    ]
    data = extract_json(
        llm.chat_complete(
            base_url, api_key, model, messages, gen_params(params),
            reasoning=DEFAULT_AUTHORING_EFFORT,
        )
    )
    return ExtractedEntities(
        characters=_coerce_entities(data.get("characters")),
        settings=_coerce_entities(data.get("settings")),
    )
