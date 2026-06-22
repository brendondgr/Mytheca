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


@router.get("/characters/{character_id}/stats", response_model=dict[str, int])
def get_character_stats(character_id: str, db: Session = Depends(get_db)):
    return stat_service.get_character_stats(db, character_id)


@router.put("/characters/{character_id}/stats", response_model=dict[str, int])
def set_character_stats(
    character_id: str, values: dict[str, int], db: Session = Depends(get_db)
):
    return stat_service.set_character_stats(db, character_id, values)
