"""Setting routes — storyline-scoped list/create, the agentic Setting Creator
endpoints (draft / scene-art prompts / scene-art render) on fixed sub-paths, then
the flat get/update/delete item routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents import setting_agent
from app.core.db import get_db
from app.schemas.setting import (
    SceneArtGenerateRequest,
    SceneArtGenerateResponse,
    SceneArtPromptRequest,
    SceneArtPromptResponse,
    SettingCreate,
    SettingDraftRequest,
    SettingDraftResponse,
    SettingRead,
    SettingUpdate,
)
from app.services import crud, scene_art

router = APIRouter(tags=["settings"])


@router.get("/storylines/{storyline_id}/settings", response_model=list[SettingRead])
def list_settings(storyline_id: str, db: Session = Depends(get_db)):
    return crud.list_settings(db, storyline_id)


@router.post(
    "/storylines/{storyline_id}/settings",
    response_model=SettingRead,
    status_code=201,
)
def create_setting(storyline_id: str, data: SettingCreate, db: Session = Depends(get_db)):
    return crud.create_setting(db, storyline_id, data)


# ---- Authoring (the agentic Setting Creator) — fixed sub-paths --------------
# Declared before ``/settings/{id}`` so "draft"/"scene-art" are not captured as ids.


@router.post("/settings/draft", response_model=SettingDraftResponse)
def draft_setting(data: SettingDraftRequest, db: Session = Depends(get_db)):
    """Draft a full setting (fields + §4.1 node metadata) from a one-line seed."""
    return setting_agent.draft_setting(db, data.seed, data.docs_overview, data.storyline_id)


@router.post("/settings/scene-art-prompts", response_model=SceneArtPromptResponse)
def setting_scene_art_prompts(data: SceneArtPromptRequest, db: Session = Depends(get_db)):
    """Write the positive/negative establishing-shot prompts for a place, in the chosen style."""
    return setting_agent.generate_scene_art_prompts(
        db,
        name=data.name,
        type=data.type,
        desc=data.desc,
        atmosphere=data.atmosphere,
        features=data.features,
        current_state=data.current_state,
        notes=data.notes,
        style=data.art_style,
    )


@router.post("/settings/scene-art", response_model=SceneArtGenerateResponse)
def setting_scene_art(data: SceneArtGenerateRequest, db: Session = Depends(get_db)):
    """Render an establishing image in the chosen art style, save it as WebP, return its URL."""
    result = scene_art.generate_scene_art(
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
    return SceneArtGenerateResponse(image=result["image"])


@router.get("/settings/{setting_id}", response_model=SettingRead)
def get_setting(setting_id: str, db: Session = Depends(get_db)):
    return crud.get_setting(db, setting_id)


@router.patch("/settings/{setting_id}", response_model=SettingRead)
def update_setting(setting_id: str, data: SettingUpdate, db: Session = Depends(get_db)):
    return crud.update_setting(db, setting_id, data)


@router.delete("/settings/{setting_id}", status_code=204)
def delete_setting(setting_id: str, db: Session = Depends(get_db)):
    crud.delete_setting(db, setting_id)
