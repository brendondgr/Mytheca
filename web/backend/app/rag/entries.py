"""Entity → lore entry adapters (brief §0.1 "one entry = one chunk").

Each Velora entity (and each persisted context document) becomes exactly one
``LoreEntry``: structured front matter built from its fields plus a body built
from its descriptive prose. Pure functions over already-loaded ORM objects — no
DB access, no embedding — so they stay trivially testable.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.rag.schema import EntryType, Frontmatter, LoreEntry

if TYPE_CHECKING:
    from app.models.character import Character
    from app.models.context_document import ContextDocument
    from app.models.scenario import Scenario
    from app.models.setting import Setting
    from app.models.storyline import Storyline

# Triage category → semantic entry type for context documents.
_CATEGORY_TYPE = {
    "character": EntryType.character,
    "setting": EntryType.location,
    "other": EntryType.lore,
}

_SUMMARY_CHARS = 280


def _split_tags(raw: str | None) -> list[str]:
    """Split a free-text trait/tag string on common separators; dedupe, drop blanks."""
    if not raw:
        return []
    parts = re.split(r"[,;·\n]+", raw)
    seen: list[str] = []
    for p in (s.strip() for s in parts):
        if p and p.lower() not in {s.lower() for s in seen}:
            seen.append(p)
    return seen


def _join(*chunks: str | None) -> str:
    """Join non-empty prose chunks with blank-line separators."""
    return "\n\n".join(c.strip() for c in chunks if c and c.strip())


def _voice_samples_text(samples: list[dict] | None) -> str:
    """Render a character's situation → single-response pairs as retrievable prose."""
    if not samples:
        return ""
    lines: list[str] = []
    for s in samples:
        situation = str((s or {}).get("situation", "")).strip()
        sample = str((s or {}).get("sample", "")).strip()
        if not sample:
            continue
        lines.append(f'Prompt: “{situation}” → {sample}' if situation else sample)
    return ("Voice samples:\n" + "\n".join(lines)) if lines else ""


def entry_from_storyline(sl: Storyline) -> LoreEntry:
    summary = (sl.tagline or "").strip() or (sl.premise or "")[:_SUMMARY_CHARS]
    fm = Frontmatter(
        id=sl.id,
        type=EntryType.lore,
        name=sl.title,
        tags=_split_tags(sl.genre),
        summary=summary,
    )
    return LoreEntry(
        fm=fm,
        body=_join(sl.premise, sl.world_primer),
        storyline_id=sl.id,
        entity_type="storyline",
        entity_id=sl.id,
    )


def entry_from_character(ch: Character) -> LoreEntry:
    summary = _join(ch.role, ch.goal and f"Goal: {ch.goal}")
    fm = Frontmatter(
        id=ch.id,
        type=EntryType.character,
        name=ch.name,
        tags=_split_tags(ch.traits),
        summary=summary[:_SUMMARY_CHARS],
    )
    body = _join(
        ch.appearance,
        ch.background,
        ch.personality,
        ch.speech and f"Speech: {ch.speech}",
        _voice_samples_text(ch.voice_samples),
        ch.secret and f"Secret: {ch.secret}",
    )
    return LoreEntry(
        fm=fm,
        body=body,
        storyline_id=ch.storyline_id,
        entity_type="character",
        entity_id=ch.id,
    )


def entry_from_setting(st: Setting) -> LoreEntry:
    fm = Frontmatter(
        id=st.id,
        type=EntryType.location,
        name=st.name,
        location=st.name,
        tags=_split_tags(st.type),
        summary=(st.desc or "")[:_SUMMARY_CHARS],
    )
    return LoreEntry(
        fm=fm,
        body=_join(st.desc, st.atmosphere, st.features, st.current_state),
        storyline_id=st.storyline_id,
        entity_type="setting",
        entity_id=st.id,
    )


def entry_from_scenario(sc: Scenario) -> LoreEntry:
    fm = Frontmatter(
        id=sc.id,
        type=EntryType.event,
        name=sc.title,
        tags=_split_tags(f"{sc.genre},{sc.tone}"),
        summary=(sc.goal or "")[:_SUMMARY_CHARS],
    )
    return LoreEntry(
        fm=fm,
        body=_join(sc.goal and f"Goal: {sc.goal}", sc.opening),
        storyline_id=sc.storyline_id,
        entity_type="scenario",
        entity_id=sc.id,
    )


def entry_from_context_document(doc: ContextDocument) -> LoreEntry:
    content = doc.content or ""
    fm = Frontmatter(
        id=doc.id,
        type=_CATEGORY_TYPE.get(doc.category, EntryType.lore),
        name=doc.name,
        summary=content[:_SUMMARY_CHARS],
    )
    return LoreEntry(
        fm=fm,
        body=content,
        storyline_id=doc.storyline_id,
        entity_type="context_document",
        entity_id=doc.id,
        include_rag=bool(doc.include_rag),
    )
