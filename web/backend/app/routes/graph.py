"""Story-Graph routes — the Type Registry (§1.4) and (Phase 4) the scenario read
path. Registry: list the types visible to a storyline (built-ins + its user
types), and create/patch/delete the user-defined ones. Built-in types are
immutable (the service rejects edits/deletes)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.graph_type import GraphTypeCreate, GraphTypeRead, GraphTypeUpdate
from app.services import type_registry

router = APIRouter(tags=["graph"])


@router.get("/storylines/{storyline_id}/graph/types", response_model=list[GraphTypeRead])
def list_graph_types(storyline_id: str, db: Session = Depends(get_db)):
    """The node/edge types visible to a storyline: global built-ins + its own."""
    return type_registry.list_types(db, storyline_id)


@router.post(
    "/storylines/{storyline_id}/graph/types",
    response_model=GraphTypeRead,
    status_code=201,
)
def create_graph_type(
    storyline_id: str, data: GraphTypeCreate, db: Session = Depends(get_db)
):
    """Register a user-defined type (starts ``experimental`` — staged per §10)."""
    return type_registry.create_user_type(db, storyline_id, data)


@router.patch("/graph/types/{type_id}", response_model=GraphTypeRead)
def update_graph_type(type_id: str, data: GraphTypeUpdate, db: Session = Depends(get_db)):
    """Edit a user-defined type (incl. promoting status experimental → trusted)."""
    return type_registry.update_user_type(db, type_id, data)


@router.delete("/graph/types/{type_id}", status_code=204)
def delete_graph_type(type_id: str, db: Session = Depends(get_db)):
    type_registry.delete_user_type(db, type_id)
