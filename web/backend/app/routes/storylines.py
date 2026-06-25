"""Storyline routes — the world container."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents import storyline_agent, triage_agent
from app.core.db import get_db
from app.schemas.context_document import TriageRequest, TriageResponse
from app.schemas.storyline import (
    StorylineCreate,
    StorylineDraftRequest,
    StorylineDraftResponse,
    StorylineRead,
    StorylineUpdate,
    WorldPrimerRequest,
    WorldPrimerResponse,
)
from app.services import crud

router = APIRouter(prefix="/storylines", tags=["storylines"])


@router.get("", response_model=list[StorylineRead])
def list_storylines(db: Session = Depends(get_db)):
    return crud.list_storylines(db)


@router.post("", response_model=StorylineRead, status_code=201)
def create_storyline(data: StorylineCreate, db: Session = Depends(get_db)):
    return crud.create_storyline(db, data)


# ---- Authoring (the agent process) — fixed sub-paths, no id collision --------


@router.post("/draft", response_model=StorylineDraftResponse)
def draft_storyline(data: StorylineDraftRequest, db: Session = Depends(get_db)):
    """Draft library metadata from a one-sentence seed (the create form prefill)."""
    return storyline_agent.draft_storyline(db, data.seed, data.docs_overview)


@router.post("/primer", response_model=WorldPrimerResponse)
def generate_world_primer(data: WorldPrimerRequest, db: Session = Depends(get_db)):
    """Generate the agent-facing World Primer from the seed + premise."""
    primer = storyline_agent.generate_world_primer(db, data.premise, data.seed, data.docs_overview)
    return WorldPrimerResponse(world_primer=primer)


@router.post("/triage", response_model=TriageResponse)
def triage_documents(data: TriageRequest, db: Session = Depends(get_db)):
    """Classify dropped reference docs → Characters / Settings / Other · Draft/RAG."""
    return triage_agent.triage_documents(db, data.docs, data.storyline_id)


@router.get("/{storyline_id}", response_model=StorylineRead)
def get_storyline(storyline_id: str, db: Session = Depends(get_db)):
    return crud.get_storyline(db, storyline_id)


@router.patch("/{storyline_id}", response_model=StorylineRead)
def update_storyline(storyline_id: str, data: StorylineUpdate, db: Session = Depends(get_db)):
    return crud.update_storyline(db, storyline_id, data)


@router.delete("/{storyline_id}", status_code=204)
def delete_storyline(storyline_id: str, db: Session = Depends(get_db)):
    crud.delete_storyline(db, storyline_id)
