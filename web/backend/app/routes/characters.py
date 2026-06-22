"""Character routes — storyline-scoped list/create, flat get/update/delete."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.character import CharacterCreate, CharacterRead, CharacterUpdate
from app.services import crud

router = APIRouter(tags=["characters"])


@router.get("/storylines/{storyline_id}/characters", response_model=list[CharacterRead])
def list_characters(storyline_id: str, db: Session = Depends(get_db)):
    return crud.list_characters(db, storyline_id)


@router.post(
    "/storylines/{storyline_id}/characters",
    response_model=CharacterRead,
    status_code=201,
)
def create_character(storyline_id: str, data: CharacterCreate, db: Session = Depends(get_db)):
    return crud.create_character(db, storyline_id, data)


@router.get("/characters/{character_id}", response_model=CharacterRead)
def get_character(character_id: str, db: Session = Depends(get_db)):
    return crud.get_character(db, character_id)


@router.patch("/characters/{character_id}", response_model=CharacterRead)
def update_character(character_id: str, data: CharacterUpdate, db: Session = Depends(get_db)):
    return crud.update_character(db, character_id, data)


@router.delete("/characters/{character_id}", status_code=204)
def delete_character(character_id: str, db: Session = Depends(get_db)):
    crud.delete_character(db, character_id)
