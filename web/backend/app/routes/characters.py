"""Character routes — storyline-scoped list/create, flat get/update/delete, plus
the agentic Character Creator endpoints (draft / portrait prompts / starting
stats), declared on fixed sub-paths before the ``/characters/{id}`` routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents import character_agent
from app.core.db import get_db
from app.schemas.character import (
    CharacterCreate,
    CharacterDraftRequest,
    CharacterDraftResponse,
    CharacterRead,
    CharacterUpdate,
    PortraitPromptRequest,
    PortraitPromptResponse,
    StartingStatsRequest,
    StartingStatsResponse,
)
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


# ---- Authoring (the agentic Character Creator) — fixed sub-paths -------------


@router.post("/characters/draft", response_model=CharacterDraftResponse)
def draft_character(data: CharacterDraftRequest, db: Session = Depends(get_db)):
    """Draft a full character (fields + base-identity prose) from a one-line seed."""
    return character_agent.draft_character(db, data.seed, data.docs_overview, data.storyline_id)


@router.post("/characters/portrait-prompts", response_model=PortraitPromptResponse)
def character_portrait_prompts(data: PortraitPromptRequest, db: Session = Depends(get_db)):
    """Write the watercolor positive/negative portrait prompts for a character."""
    return character_agent.generate_portrait_prompts(
        db,
        name=data.name,
        role=data.role,
        appearance=data.appearance,
        traits=data.traits,
        personality=data.personality,
        species=data.species,
        notes=data.notes,
    )


@router.post("/characters/starting-stats", response_model=StartingStatsResponse)
def character_starting_stats(data: StartingStatsRequest, db: Session = Depends(get_db)):
    """Propose starting stat values keyed to the storyline's stat definitions."""
    return character_agent.propose_starting_stats(
        db,
        data.storyline_id,
        name=data.name,
        role=data.role,
        traits=data.traits,
        personality=data.personality,
        background=data.background,
    )


@router.get("/characters/{character_id}", response_model=CharacterRead)
def get_character(character_id: str, db: Session = Depends(get_db)):
    return crud.get_character(db, character_id)


@router.patch("/characters/{character_id}", response_model=CharacterRead)
def update_character(character_id: str, data: CharacterUpdate, db: Session = Depends(get_db)):
    return crud.update_character(db, character_id, data)


@router.delete("/characters/{character_id}", status_code=204)
def delete_character(character_id: str, db: Session = Depends(get_db)):
    crud.delete_character(db, character_id)
