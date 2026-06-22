"""Stat services.

Stat *definitions* are owned by the storyline; the range (min/max/default/
visibility) is locked at creation so PATCH only touches descriptive fields.
Character stat *values* are upserted and **clamped** to the definition's range —
the AI can never push a value out of bounds — and unknown keys are rejected.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.core.ids import new_id
from app.models import CharacterStat, StatDefinition
from app.schemas.stat import StatDefinitionCreate, StatDefinitionUpdate
from app.services.crud import get_character, get_storyline

# ---- stat definitions (per storyline) --------------------------------------


def list_stat_definitions(db: Session, storyline_id: str) -> list[StatDefinition]:
    get_storyline(db, storyline_id)
    return list(
        db.scalars(
            select(StatDefinition)
            .where(StatDefinition.storyline_id == storyline_id)
            .order_by(StatDefinition.key)
        )
    )


def _get_definition(db: Session, storyline_id: str, key: str) -> StatDefinition:
    sd = db.scalar(
        select(StatDefinition).where(
            StatDefinition.storyline_id == storyline_id, StatDefinition.key == key
        )
    )
    if sd is None:
        raise APIError(404, "not_found", f"Stat '{key}' not found in storyline '{storyline_id}'.")
    return sd


def create_stat_definition(
    db: Session, storyline_id: str, data: StatDefinitionCreate
) -> StatDefinition:
    get_storyline(db, storyline_id)
    if db.scalar(
        select(StatDefinition).where(
            StatDefinition.storyline_id == storyline_id, StatDefinition.key == data.key
        )
    ):
        raise APIError(409, "conflict", f"Stat '{data.key}' already exists in this storyline.")
    sd = StatDefinition(
        id=new_id("stat"),
        storyline_id=storyline_id,
        key=data.key,
        display_name=data.display_name,
        description=data.description,
        min=data.min,
        max=data.max,
        default=data.default,
        visibility=data.visibility,
        guidance=data.guidance,
        applies_to=list(data.applies_to),
    )
    db.add(sd)
    db.commit()
    db.refresh(sd)
    return sd


def update_stat_definition(
    db: Session, storyline_id: str, key: str, data: StatDefinitionUpdate
) -> StatDefinition:
    sd = _get_definition(db, storyline_id, key)
    # StatDefinitionUpdate only carries descriptive fields — the range is locked.
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(sd, field, value)
    db.commit()
    db.refresh(sd)
    return sd


# ---- character stat values (clamped) ---------------------------------------


def get_character_stats(db: Session, character_id: str) -> dict[str, int]:
    get_character(db, character_id)
    rows = db.scalars(select(CharacterStat).where(CharacterStat.character_id == character_id))
    return {row.key: row.value for row in rows}


def set_character_stats(
    db: Session, character_id: str, values: dict[str, int]
) -> dict[str, int]:
    char = get_character(db, character_id)
    definitions = {
        d.key: d
        for d in db.scalars(
            select(StatDefinition).where(StatDefinition.storyline_id == char.storyline_id)
        )
    }
    unknown = [key for key in values if key not in definitions]
    if unknown:
        raise APIError(422, "unknown_stat", "Unknown stat key(s) for this storyline.", {"keys": unknown})

    existing = {
        row.key: row
        for row in db.scalars(
            select(CharacterStat).where(CharacterStat.character_id == character_id)
        )
    }
    for key, raw in values.items():
        definition = definitions[key]
        clamped = max(definition.min, min(definition.max, int(raw)))
        if key in existing:
            existing[key].value = clamped
        else:
            db.add(CharacterStat(id=new_id("cs"), character_id=character_id, key=key, value=clamped))
    db.commit()
    return get_character_stats(db, character_id)
