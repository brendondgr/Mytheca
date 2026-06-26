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

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.agents._common import extract_json, gen_params, resolve_llm, world_context
from app.core.errors import APIError
from app.schemas.context_document import (
    TriageDoc,
    TriageDoneEvent,
    TriageEvent,
    TriageItem,
    TriageItemEvent,
    TriageResponse,
    TriageStatusEvent,
)
from app.schemas.settings import LlmParams
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

# Single-document variant for the live (per-file) triage stream — one LLM call
# per file so each row can be classified in front of the author.
_TRIAGE_ONE_SYSTEM = (
    "You are Velora's worldbuilding triage assistant. Classify the SINGLE "
    "reference document below for an interactive-fiction world and recommend how "
    "it should be used. Respond with ONLY a JSON object — no prose, no markdown, "
    "no code fences — of the form "
    '{"category": "character"|"setting"|"other", "includeDraft": true|false, '
    '"includeRag": true|false, "rationale": "<one short line>"}.\n'
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
    "false.\n"
    "- includeRag: true for essentially every real document; false only for empty "
    "or clearly irrelevant content."
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


# ---- live (per-file) triage stream -----------------------------------------


def classify_document(
    doc: TriageDoc,
    *,
    base_url: str,
    api_key: str,
    model: str,
    params: LlmParams,
    world_ctx: str = "",
) -> TriageItem:
    """Classify ONE document with a single LLM call (the live-stream primitive)."""
    snippet = (doc.text or "").strip()[:_DOC_SNIPPET]
    user = f"Document name: {doc.name}\n\nContent:\n{snippet}{world_ctx}"
    messages = [
        {"role": "system", "content": _TRIAGE_ONE_SYSTEM},
        {"role": "user", "content": user},
    ]
    data = extract_json(llm.chat_complete(base_url, api_key, model, messages, gen_params(params)))
    return _coerce_item(doc.name, data)


def validate_triage_inputs(db: Session, docs: list[TriageDoc]) -> None:
    """Pre-flight for the stream: require a configured LLM only when there is work.

    Empty/blank doc sets need no model (they stream straight to ``done``), so an
    unconfigured LLM is fine then; otherwise this raises a normal ``400`` before the
    200 stream opens (status can't change once it has).
    """
    if any((d.text or "").strip() for d in docs):
        resolve_llm(db)


def iter_triage_documents(
    db: Session, docs: list[TriageDoc], storyline_id: str | None = None
) -> Iterator[TriageEvent]:
    """Classify each document one at a time, yielding a progress event per file.

    Genuinely live (one LLM call per doc). A per-doc failure falls back to
    Other/RAG-on rather than aborting the whole run — so one bad file never sinks
    the rest of the triage. Errors that escape (e.g. an unconfigured LLM surfacing
    only here) propagate; the route wraps them into a terminal ``error`` event.
    """
    docs = [d for d in docs if (d.text or "").strip()]
    if not docs:
        yield TriageDoneEvent()
        return

    base_url, api_key, model, params = resolve_llm(db)
    world_ctx = world_context(db, storyline_id)
    total = len(docs)
    for i, doc in enumerate(docs):
        yield TriageStatusEvent(name=doc.name, index=i, total=total)
        try:
            item = classify_document(
                doc,
                base_url=base_url,
                api_key=api_key,
                model=model,
                params=params,
                world_ctx=world_ctx,
            )
        except APIError:
            item = _fallback(doc.name)
        yield TriageItemEvent(item=item)
    yield TriageDoneEvent()
