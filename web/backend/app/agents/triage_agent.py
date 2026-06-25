"""Triage agent — classify dropped reference documents for the New Storyline page.

One creation-time operation over the configured LLM (same proxy + settings-store
resolution as the other authoring agents, via ``agents._common``):

* ``triage_documents`` — sort each dropped ``.txt``/``.md`` document into one of
  three buckets and recommend its inclusion tiers:

  - **category** ``character`` — the doc is primarily about ONE character;
    ``setting`` — primarily about ONE place; ``other`` — it covers MULTIPLE
    characters or settings, mixes them, or is general world lore/history/rules.
  - **includeDraft** — true only for world-setting/lore documents that should
    ground drafting; most docs are false.
  - **includeRag** — the retrieval corpus; default on for everything real.

The classification is returned for review; the documents are persisted later by
the page (``ContextDocument`` bulk create). No retrieval happens here.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents._common import extract_json, gen_params, resolve_llm, world_context
from app.schemas.context_document import TriageDoc, TriageItem, TriageResponse
from app.services import llm

# Per-document snippet cap: classification needs the gist, not the whole file.
_DOC_SNIPPET = 1500
# Total cap on the assembled triage prompt (mirrors _common.DOCS_CAP).
_TOTAL_CAP = 8000

_VALID_CATEGORIES = {"character", "setting", "other"}

_TRIAGE_SYSTEM = (
    "You are Velora's worldbuilding triage assistant. You are given several "
    "reference documents for an interactive-fiction world. Classify EACH document "
    "and recommend how it should be used. Respond with ONLY a JSON object — no "
    "prose, no markdown, no code fences — of the form "
    '{"items": [{"name": "<the document name exactly as given>", "category": '
    '"character"|"setting"|"other", "includeDraft": true|false, "includeRag": '
    'true|false, "rationale": "<one short line>"}]}.\n'
    "Rules for category:\n"
    "- 'character' — the document is primarily about ONE character (a single "
    "person, being, or creature).\n"
    "- 'setting' — the document is primarily about ONE place or location.\n"
    "- 'other' — it describes MULTIPLE characters or MULTIPLE settings, mixes "
    "characters and places, or is general world material (history, lore, rules, "
    "factions, timelines, glossaries).\n"
    "Rules for inclusion:\n"
    "- includeDraft: true ONLY when the document describes the world's setting, "
    "tone, lore, or rules and should ground how the world is drafted; otherwise "
    "false (most character/setting/reference sheets are false).\n"
    "- includeRag: true for essentially every real document (it is the retrieval "
    "corpus); set false only for empty or clearly irrelevant content.\n"
    "Return exactly one item per input document, using the document's name verbatim."
)


def _build_user(docs: list[TriageDoc]) -> str:
    """Assemble the documents into one bounded triage prompt."""
    parts: list[str] = []
    used = 0
    for doc in docs:
        snippet = (doc.text or "").strip()[:_DOC_SNIPPET]
        block = f"### {doc.name}\n{snippet}"
        if used + len(block) > _TOTAL_CAP:
            block = block[: max(0, _TOTAL_CAP - used)]
        parts.append(block)
        used += len(block)
        if used >= _TOTAL_CAP:
            break
    return "Documents:\n\n" + "\n\n".join(parts)


def _coerce_item(name: str, row: dict) -> TriageItem:
    """Build a TriageItem from a model row, defaulting anything malformed."""
    category = str(row.get("category") or "").strip().lower()
    if category not in _VALID_CATEGORIES:
        category = "other"
    return TriageItem(
        name=name,
        category=category,  # type: ignore[arg-type]
        include_draft=bool(row.get("includeDraft", row.get("include_draft", False))),
        include_rag=bool(row.get("includeRag", row.get("include_rag", True))),
        rationale=str(row.get("rationale") or "").strip(),
    )


def _fallback(name: str) -> TriageItem:
    """Default classification for a doc the model skipped: Other, RAG-on."""
    return TriageItem(name=name, category="other", include_draft=False, include_rag=True)


def triage_documents(
    db: Session, docs: list[TriageDoc], storyline_id: str | None = None
) -> TriageResponse:
    """Classify each document → category + Draft/RAG inclusion (review-only)."""
    docs = [d for d in docs if (d.text or "").strip()]
    if not docs:
        return TriageResponse(items=[])

    base_url, api_key, model, params = resolve_llm(db)
    user = _build_user(docs) + world_context(db, storyline_id)
    messages = [
        {"role": "system", "content": _TRIAGE_SYSTEM},
        {"role": "user", "content": user},
    ]
    data = extract_json(llm.chat_complete(base_url, api_key, model, messages, gen_params(params)))

    raw = data.get("items")
    rows = raw if isinstance(raw, list) else []
    by_name: dict[str, dict] = {}
    for row in rows:
        if isinstance(row, dict):
            key = str(row.get("name") or "").strip()
            if key:
                by_name[key] = row

    # Preserve input order; fall back per-doc for anything the model dropped.
    items = [
        _coerce_item(d.name, by_name[d.name]) if d.name in by_name else _fallback(d.name)
        for d in docs
    ]
    return TriageResponse(items=items)
