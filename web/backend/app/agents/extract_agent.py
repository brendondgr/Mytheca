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
    DOCS_CAP,
    LlmConn,
    extract_json,
    gen_params,
    resolve_llm_or,
)
from app.schemas.build import ExtractedEntities, ExtractedEntity
from app.schemas.reasoning import ReasoningEffort
from app.services import llm

# Per-subject source brief is bounded so a multi-entity doc can't blow the prompt
# budget of the downstream draft calls.
_SOURCE_CAP = 4000

# Strict, named-only extraction. The build must NOT invent people/places out of lore
# by "expanding context" — it may only surface subjects the document itself explicitly
# names and profiles. Returning nothing for a lore/history/rules document is correct.
_EXTRACT_SYSTEM = (
    "You are Velora's entity-extraction assistant for an interactive-fiction world. "
    "You are given ONE reference document. Return ONLY the subjects the document "
    "EXPLICITLY NAMES with a proper name AND genuinely PROFILES (describes as their own "
    "subject in enough depth to build a card). Respond with ONLY a JSON object — no "
    "prose, no markdown, no code fences — of the form "
    '{"characters": [{"name": "<proper name>", "source": "<a self-contained paragraph '
    "describing ONLY this one character, drawn STRICTLY from the document: who they "
    'are, role, appearance, personality, goals>"}], "settings": [{"name": "<proper '
    'place name>", "source": "<a self-contained paragraph describing ONLY this one '
    'place, strictly from the document>"}]}.\n'
    "STRICT RULES — follow exactly:\n"
    "- Include a subject ONLY if it is explicitly NAMED with a proper name in the "
    "document and is genuinely described there as its own subject.\n"
    "- Do NOT invent, infer, expand, or extrapolate. Do NOT manufacture a character or "
    "place out of general context, lore, history, rules, factions, events, timelines, "
    "or world-building terms. A name only MENTIONED in passing (not profiled) is NOT a "
    "subject — leave it out.\n"
    "- If the document has no explicitly named, profile-worthy character or place "
    "(e.g. it is lore, history, rules, a glossary, a timeline, or atmosphere), return "
    "empty lists. Returning nothing is correct and expected for such documents.\n"
    "- Every 'source' must be drawn strictly from the document (add no facts) and must "
    "stand alone — a later agent drafts the card from it without seeing the original.\n"
    "- One entry per distinct named subject; never duplicate a subject."
)

_KIND_INSTRUCTION = {
    "character": (
        "\n\nThis document was classified as a CHARACTER. Extract ONLY named "
        "characters (people/beings) — usually exactly ONE (the document's subject); "
        "return several ONLY if it clearly names several distinct people. Always "
        'return "settings" as an empty list.'
    ),
    "setting": (
        "\n\nThis document was classified as a SETTING. Extract ONLY named settings "
        "(places/locations) — usually exactly ONE; return several ONLY if it clearly "
        'names several distinct places. Always return "characters" as an empty list.'
    ),
    "both": (
        "\n\nThis document is uncategorized. Extract any explicitly named, "
        "profile-worthy characters AND settings, following the strict rules. If it "
        "names none (it is only lore/history/context), return empty lists."
    ),
}


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
    conn: LlmConn | None = None,
    kind: str = "both",
) -> ExtractedEntities:
    """Extract the explicitly NAMED characters/settings a document profiles.

    Strict + named-only: it never invents or expands a subject out of lore — a
    document with no explicitly named, profile-worthy subject yields empty lists. Blank
    input short-circuits to empty lists (no LLM call).

    ``kind`` scopes what to look for, matching the author's triage bucket: a
    ``"character"``-bucket doc is mined only for named characters, a ``"setting"`` doc
    only for named settings, and an uncategorized (``"both"``) doc for either. The
    off-kind list is always returned empty (defensively cleared even if the model
    over-produces), so a Character doc can never inject a phantom setting.

    Best-effort at the orchestration layer (the build wraps the call, retries/skips a
    doc whose reply won't parse), but a malformed JSON reply still raises through
    ``extract_json`` so the caller can decide. ``conn`` — pass a pre-resolved LLM
    connection (``_common.resolve_llm_or``) so this can run on a worker thread without
    touching the request ``Session``. Runs at **LOW** reasoning effort (segmentation —
    faster, far less likely to truncate the JSON mid-object).
    """
    text = (doc_text or "").strip()
    if not text:
        return ExtractedEntities()

    base_url, api_key, model, params = resolve_llm_or(db, conn)
    header = f"Document name: {doc_name}\n\n" if doc_name else ""
    ground = f"\n\nWorld context (for consistency only):\n{grounding.strip()}" if grounding else ""
    instruction = _KIND_INSTRUCTION.get(kind, _KIND_INSTRUCTION["both"])
    user = f"{header}Document content:\n{text[:DOCS_CAP]}{ground}{instruction}"
    messages = [
        {"role": "system", "content": _EXTRACT_SYSTEM},
        {"role": "user", "content": user},
    ]
    data = extract_json(
        llm.chat_complete(
            base_url, api_key, model, messages, gen_params(params),
            reasoning=ReasoningEffort.LOW,
        )
    )
    # Enforce the kind scope: a Character doc yields only characters, a Setting doc only
    # settings — never let the model's off-kind list leak a phantom entity.
    characters = _coerce_entities(data.get("characters")) if kind != "setting" else []
    settings = _coerce_entities(data.get("settings")) if kind != "character" else []
    return ExtractedEntities(characters=characters, settings=settings)
