"""Setting routes — storyline-scoped list/create, flat get/update/delete."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.setting import SettingCreate, SettingRead, SettingUpdate
from app.services import crud

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


@router.get("/settings/{setting_id}", response_model=SettingRead)
def get_setting(setting_id: str, db: Session = Depends(get_db)):
    return crud.get_setting(db, setting_id)


@router.patch("/settings/{setting_id}", response_model=SettingRead)
def update_setting(setting_id: str, data: SettingUpdate, db: Session = Depends(get_db)):
    return crud.update_setting(db, setting_id, data)


@router.delete("/settings/{setting_id}", status_code=204)
def delete_setting(setting_id: str, db: Session = Depends(get_db)):
    crud.delete_setting(db, setting_id)
