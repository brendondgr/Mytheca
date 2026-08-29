"""Apply an approved storyline-edit plan — the implement half of plan → implement.

The write authority stays the form's: text/primer fields land on the storyline row,
statistics route through the stat services' existing clamping/validation. Everything
runs in **one transaction** (partial failure rolls the whole plan back), guarded by:

1. the **diff guard** (a backstop re-check that no change lies outside the write scope),
2. a **stale-read reconcile** — the plan's ``base_version`` content hash must still match
   the storyline, or the apply is rejected (409) rather than clobbering a concurrent edit.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agents.storyline_edit.scope import diff_guard, writable_keys
from app.core.errors import APIError
from app.models import Storyline
from app.rag import indexer as rag_index
from app.schemas.stat import StatDefinitionCreate, StatDefinitionUpdate
from app.schemas.storyline_edit import ScopeState, StatChange, StoryPlan
from app.services import crud, stats, style_guide

# plan field key (camel) → the storyline attribute it writes.
_FIELD_ATTR = {
    "title": "title",
    "genre": "genre",
    "tagline": "tagline",
    "premise": "premise",
    "worldPrimer": "world_primer",
}


def storyline_version(db: Session, sl: Storyline, writable: set[str]) -> str:
    """A content hash of the writable fields — the concurrency token for reconcile.

    Computed the same way at plan time and at apply time, so the client can echo it
    to prove nothing changed underneath the plan. Narrowed to the writable set so an
    unrelated change to an out-of-scope field never blocks an in-scope apply.
    """
    parts: dict[str, object] = {}
    if "styleBlocks" in writable:
        # In the concurrency token too: without it, two assistants editing the guide would
        # both pass the staleness check and the second would overwrite the first. Sorted,
        # because a dict's order is not a fact about its content.
        parts["styleBlocks"] = sorted((sl.style_blocks or {}).items())
    for key, attr in _FIELD_ATTR.items():
        if key in writable:
            parts[key] = getattr(sl, attr)
    if "statistics" in writable:
        parts["stats"] = sorted(
            (
                {
                    "key": d.key,
                    "displayName": d.display_name,
                    "description": d.description,
                    "min": d.min,
                    "max": d.max,
                    "default": d.default,
                    "visibility": d.visibility,
                    "guidance": d.guidance,
                    "appliesTo": d.applies_to,
                    "bands": d.bands,
                }
                for d in stats.list_stat_definitions(db, sl.id)
            ),
            key=lambda row: str(row["key"]),
        )
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def apply_plan(
    db: Session,
    storyline_id: str,
    scope: ScopeState,
    plan: StoryPlan,
    base_version: str | None,
) -> tuple[Storyline, list[str]]:
    """Apply the approved plan transactionally; return the fresh row + an audit list."""
    sl = crud.get_storyline(db, storyline_id)  # 404
    diff_guard(plan, scope)  # backstop: reject any out-of-scope change

    writable = writable_keys(scope)
    if base_version and base_version != storyline_version(db, sl, writable):
        raise APIError(
            409,
            "stale_storyline",
            "The storyline changed since this plan was made — reopen the assistant and try again.",
        )

    applied: list[str] = []
    try:
        text_patch: dict[str, str] = {}
        for change in plan.changes:
            attr = _FIELD_ATTR.get(change.field)
            if attr is None:
                continue
            text_patch[attr] = change.after or ""
            applied.append(f"Updated {change.field}")
        for attr, value in text_patch.items():
            setattr(sl, attr, value)

        if plan.style_changes:
            # Applied block by block onto whatever the row holds, so an approved change to
            # one block never silently drops the five the agent did not mention.
            blocks = dict(style_guide.normalize_blocks(sl.style_blocks))
            for change in plan.style_changes:
                if change.after:
                    blocks[change.block] = change.after
                    applied.append(f"Updated narrative style / {change.block}")
                else:
                    blocks.pop(change.block, None)
                    applied.append(f"Removed narrative style / {change.block}")
            sl.style_blocks = style_guide.normalize_blocks(blocks) or None

        for stat_change in plan.stat_changes:
            applied.append(_apply_stat_change(db, storyline_id, stat_change))

        db.flush()
        db.commit()
    except APIError:
        db.rollback()
        raise
    except Exception:  # pragma: no cover - defensive; keep the storyline whole
        db.rollback()
        raise APIError(422, "apply_failed", "The edit could not be applied.")

    db.refresh(sl)
    rag_index.sync_storyline(sl)  # best-effort re-embed (mirrors crud.update_storyline)
    return sl, applied


def _apply_stat_change(db: Session, storyline_id: str, change: StatChange) -> str:
    if change.change_type == "remove":
        stats.delete_stat_definition(db, storyline_id, change.key, commit=False)
        return f"Removed stat {change.key}"

    if change.after is None:
        raise APIError(422, "invalid_stat", f"Stat '{change.key}' change is missing its new definition.")
    payload = change.after.model_dump()

    if change.change_type == "add":
        try:
            create = StatDefinitionCreate(**payload)
        except ValidationError as exc:
            raise APIError(422, "invalid_stat", f"Stat '{change.key}' is invalid.", {"errors": exc.errors()})
        stats.create_stat_definition(db, storyline_id, create, commit=False)
        return f"Added stat {change.key}"

    # update — only descriptive/range fields; key is immutable.
    payload.pop("key", None)
    try:
        update = StatDefinitionUpdate(**payload)
    except ValidationError as exc:
        raise APIError(422, "invalid_stat", f"Stat '{change.key}' is invalid.", {"errors": exc.errors()})
    stats.update_stat_definition(db, storyline_id, change.key, update, commit=False)
    return f"Updated stat {change.key}"
