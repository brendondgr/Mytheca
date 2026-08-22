"""Stat routes — definitions on the storyline, clamped values on the character."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.stat import StatDefinitionCreate, StatDefinitionRead, StatDefinitionUpdate
from app.services import stats as stat_service

router = APIRouter(tags=["stats"])


@router.get("/storylines/{storyline_id}/stats", response_model=list[StatDefinitionRead])
def list_stats(storyline_id: str, db: Session = Depends(get_db)):
    return stat_service.list_stat_definitions(db, storyline_id)


@router.post(
    "/storylines/{storyline_id}/stats",
    response_model=StatDefinitionRead,
    status_code=201,
)
def create_stat(storyline_id: str, data: StatDefinitionCreate, db: Session = Depends(get_db)):
    return stat_service.create_stat_definition(db, storyline_id, data)


@router.patch("/storylines/{storyline_id}/stats/{key}", response_model=StatDefinitionRead)
def update_stat(
    storyline_id: str, key: str, data: StatDefinitionUpdate, db: Session = Depends(get_db)
):
    return stat_service.update_stat_definition(db, storyline_id, key, data)


@router.delete("/storylines/{storyline_id}/stats/{key}", status_code=204)
def delete_stat(storyline_id: str, key: str, db: Session = Depends(get_db)):
    stat_service.delete_stat_definition(db, storyline_id, key)


@router.get("/characters/{character_id}/stats", response_model=dict[str, int])
def get_character_stats(character_id: str, db: Session = Depends(get_db)):
    return stat_service.get_character_stats(db, character_id)


@router.put("/characters/{character_id}/stats", response_model=dict[str, int])
def set_character_stats(
    character_id: str, values: dict[str, int], db: Session = Depends(get_db)
):
    """The authoring write: this is the author saying what the character starts with."""
    return stat_service.set_character_stats(db, character_id, values, authored=True)


@router.post("/characters/{character_id}/stats/reset", response_model=dict[str, int])
def reset_character_stats(character_id: str, db: Session = Depends(get_db)):
    """Put a character back to the values they were written with.

    The only way back from ``session_stats.carry_forward``, which overwrites the authored
    value in place when a play-through closes. A stat that has never carried has no captured
    baseline and resets to itself, so this is safe on a whole cast without knowing what any
    of them have been through.
    """
    return stat_service.reset_character_stats(db, character_id)
