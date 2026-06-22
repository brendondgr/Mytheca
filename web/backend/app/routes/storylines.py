"""Storyline routes — the world container."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.storyline import StorylineCreate, StorylineRead, StorylineUpdate
from app.services import crud

router = APIRouter(prefix="/storylines", tags=["storylines"])


@router.get("", response_model=list[StorylineRead])
def list_storylines(db: Session = Depends(get_db)):
    return crud.list_storylines(db)


@router.post("", response_model=StorylineRead, status_code=201)
def create_storyline(data: StorylineCreate, db: Session = Depends(get_db)):
    return crud.create_storyline(db, data)


@router.get("/{storyline_id}", response_model=StorylineRead)
def get_storyline(storyline_id: str, db: Session = Depends(get_db)):
    return crud.get_storyline(db, storyline_id)


@router.patch("/{storyline_id}", response_model=StorylineRead)
def update_storyline(storyline_id: str, data: StorylineUpdate, db: Session = Depends(get_db)):
    return crud.update_storyline(db, storyline_id, data)


@router.delete("/{storyline_id}", status_code=204)
def delete_storyline(storyline_id: str, db: Session = Depends(get_db)):
    crud.delete_storyline(db, storyline_id)
