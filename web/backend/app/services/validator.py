"""Turn-loop validator — parse + validate + clamp a proposed stat change.

A character may propose a stat change (a ``<type:state_update>`` block carrying a stat
JSON). The validator parses it tolerantly, confirms the stat **exists** for the world,
resolves the new value (explicit ``value`` or ``delta`` applied to the current value),
and **clamps** it to the definition's ``[min, max]`` — keeping the free-text ``reason``
as an audit trail. An unknown stat is **dropped** (returns ``None``), so the model can
never push an undefined or out-of-range value through.

The clamped result is what the engine applies on the hot path and emits as the
``state_update`` event. (A repair-loop — re-asking the model on malformed output — is a
recorded fallback seam; the thin-tag emission rarely needs it.)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agents.relationship_agent import RELATIONSHIP_TYPES
from app.events.envelope import StatPatch
from app.models.stat import StatDefinition
from app.services import stats


def _loads(raw: str) -> dict | None:
    """Tolerantly parse a stat JSON block (strip fences/surrounds); ``None`` on failure."""
    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _definition(db: Session, storyline_id: str, key: str) -> StatDefinition | None:
    for sd in stats.list_stat_definitions(db, storyline_id):
        if sd.key == key:
            return sd
    return None


def validate_stat(
    db: Session,
    storyline_id: str,
    character_id: str,
    raw: str,
) -> StatPatch | None:
    """Validate + clamp a proposed stat change; ``None`` when invalid/unknown (dropped)."""
    data = _loads(raw)
    if not data:
        return None
    key = str(data.get("key", "")).strip()
    if not key:
        return None
    definition = _definition(db, storyline_id, key)
    if definition is None:
        return None  # unknown stat — dropped (the model can't invent a stat)

    current = stats.get_character_stats(db, character_id).get(key, definition.default)
    if data.get("value") is not None:
        try:
            target = int(data["value"])
        except (ValueError, TypeError):
            return None
    elif data.get("delta") is not None:
        try:
            target = current + int(data["delta"])
        except (ValueError, TypeError):
            return None
    else:
        return None  # neither value nor delta → nothing to apply

    clamped = max(definition.min, min(definition.max, target))
    return StatPatch(
        character_id=character_id,
        key=key,
        delta=clamped - current,
        value=clamped,
        reason=str(data.get("reason", "")),
    )


@dataclass
class RelationshipPatch:
    """A validated directed relationship change (speaker → type → target)."""

    source_id: str
    type: str
    target_id: str
    reason: str = ""


def validate_relationship(
    source_id: str,
    raw: str,
    *,
    cast: list[tuple[str, str]],
) -> RelationshipPatch | None:
    """Validate a proposed ``<type:relationship_update>`` block (Reactive Turn Director P5).

    Confirms the type is a known character↔character edge and the ``target`` names a real
    cast member (exact, else fuzzy); ``None`` when unknown/malformed/self-directed so the
    model can never write an invalid edge. ``cast`` is ``[(id, name), …]``.
    """
    data = _loads(raw)
    if not data:
        return None
    etype = str(data.get("type", "")).strip().lower()
    if etype not in RELATIONSHIP_TYPES:
        return None
    target_name = str(data.get("target", "")).strip().lower()
    if not target_name:
        return None
    target_id = next((cid for cid, name in cast if name.lower() == target_name), None)
    if target_id is None:  # fuzzy fallback — the model may give a partial/qualified name
        target_id = next(
            (cid for cid, name in cast if target_name in name.lower() or name.lower() in target_name),
            None,
        )
    if target_id is None or target_id == source_id:
        return None
    return RelationshipPatch(source_id, etype, target_id, str(data.get("reason", "")))
