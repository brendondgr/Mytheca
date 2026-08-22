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
    PortraitGenerateRequest,
    PortraitGenerateResponse,
    PortraitPromptRequest,
    PortraitPromptResponse,
    StartingStatsRequest,
    StartingStatsResponse,
    VoiceSamplesRequest,
    VoiceSamplesResponse,
)
from app.services import crud, portraits

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
    """Write the positive/negative portrait prompts for a character, in the chosen style."""
    return character_agent.generate_portrait_prompts(
        db,
        name=data.name,
        role=data.role,
        appearance=data.appearance,
        traits=data.traits,
        personality=data.personality,
        species=data.species,
        notes=data.notes,
        style=data.art_style,
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


@router.post("/characters/voice-samples", response_model=VoiceSamplesResponse)
def character_voice_samples(data: VoiceSamplesRequest, db: Session = Depends(get_db)):
    """Derive a voice & tone profile (situation → sample-response pairs) — before stats."""
    return character_agent.propose_voice_samples(
        db,
        name=data.name,
        role=data.role,
        traits=data.traits,
        speech=data.speech,
        background=data.background,
        personality=data.personality,
        storyline_id=data.storyline_id,
    )


@router.post("/characters/portrait", response_model=PortraitGenerateResponse)
def character_portrait(data: PortraitGenerateRequest, db: Session = Depends(get_db)):
    """Render a portrait via ComfyUI in the chosen art style, save it as WebP, return its URL."""
    result = portraits.generate_portrait(
        db,
        data.positive,
        data.negative,
        base_url=data.base_url,
        workflow=data.workflow,
        width=data.width,
        height=data.height,
        steps=data.steps,
        cfg=data.cfg,
        style=data.art_style,
    )
    return PortraitGenerateResponse(portrait=result["portrait"])


@router.get("/characters/{character_id}", response_model=CharacterRead)
def get_character(character_id: str, db: Session = Depends(get_db)):
    return crud.get_character(db, character_id)


@router.patch("/characters/{character_id}", response_model=CharacterRead)
def update_character(character_id: str, data: CharacterUpdate, db: Session = Depends(get_db)):
    return crud.update_character(db, character_id, data)


@router.delete("/characters/{character_id}", status_code=204)
def delete_character(character_id: str, db: Session = Depends(get_db)):
    crud.delete_character(db, character_id)
