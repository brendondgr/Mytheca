"""Scenario routes — storyline-scoped list/create, flat get/update/delete."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents import scenario_agent
from app.core.db import get_db
from app.schemas.scenario import (
    ScenarioCreate,
    ScenarioDraftRequest,
    ScenarioDraftResponse,
    ScenarioGraphRead,
    ScenarioRead,
    ScenarioSceneArtPromptRequest,
    ScenarioUpdate,
)
from app.schemas.setting import (
    SceneArtGenerateRequest,
    SceneArtGenerateResponse,
    SceneArtPromptResponse,
)
from app.services import crud, graph_reader, scene_art

router = APIRouter(tags=["scenarios"])


@router.get("/storylines/{storyline_id}/scenarios", response_model=list[ScenarioRead])
def list_scenarios(storyline_id: str, db: Session = Depends(get_db)):
    return crud.list_scenarios(db, storyline_id)


@router.post(
    "/storylines/{storyline_id}/scenarios",
    response_model=ScenarioRead,
    status_code=201,
)
def create_scenario(storyline_id: str, data: ScenarioCreate, db: Session = Depends(get_db)):
    return crud.create_scenario(db, storyline_id, data)


# ---- Authoring (the agentic Scenario Creator) — fixed sub-path ---------------
# Declared before the dynamic ``/scenarios/{scenario_id}`` routes below, or the
# dynamic segment would shadow ``/scenarios/draft``.


@router.post("/scenarios/draft", response_model=ScenarioDraftResponse)
def draft_scenario(data: ScenarioDraftRequest, db: Session = Depends(get_db)):
    """Draft a scenario (fields + a roster-grounded cast & setting) from a seed."""
    return scenario_agent.draft_scenario(db, data.seed, data.docs_overview, data.storyline_id)


@router.post("/scenarios/scene-art-prompts", response_model=SceneArtPromptResponse)
def scenario_scene_art_prompts(data: ScenarioSceneArtPromptRequest, db: Session = Depends(get_db)):
    """Write the positive/negative prompts for a scenario establishing shot, in the chosen style."""
    return scenario_agent.generate_scene_art_prompts(
        db,
        title=data.title,
        genre=data.genre,
        tone=data.tone,
        goal=data.goal,
        opening=data.opening,
        setting_name=data.setting_name,
        setting_desc=data.setting_desc,
        notes=data.notes,
        style=data.art_style,
    )


@router.post("/scenarios/scene-art", response_model=SceneArtGenerateResponse)
def scenario_scene_art(data: SceneArtGenerateRequest, db: Session = Depends(get_db)):
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


@router.get("/scenarios/{scenario_id}", response_model=ScenarioRead)
def get_scenario(scenario_id: str, db: Session = Depends(get_db)):
    return crud.get_scenario(db, scenario_id)


@router.get("/scenarios/{scenario_id}/graph", response_model=ScenarioGraphRead)
def get_scenario_graph(scenario_id: str, db: Session = Depends(get_db)):
    """Load the scenario's Story-Graph subgraph (cast + setting + edges), read live
    from Neo4j (§7.2). ``available`` is False when the graph is off/unreachable."""
    return graph_reader.scenario_graph(db, scenario_id)


@router.patch("/scenarios/{scenario_id}", response_model=ScenarioRead)
def update_scenario(scenario_id: str, data: ScenarioUpdate, db: Session = Depends(get_db)):
    return crud.update_scenario(db, scenario_id, data)


@router.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: str, db: Session = Depends(get_db)):
    crud.delete_scenario(db, scenario_id)
