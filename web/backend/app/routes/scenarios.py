"""Scenario routes — storyline-scoped list/create, flat get/update/delete."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.scenario import (
    ScenarioCreate,
    ScenarioGraphRead,
    ScenarioRead,
    ScenarioUpdate,
)
from app.services import crud, graph_reader

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
