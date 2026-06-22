"""Setting request/response schemas."""

from __future__ import annotations

from app.schemas.base import CamelModel


class SettingBase(CamelModel):
    name: str
    type: str = "Social Hub"
    desc: str = "A place yet to be described."


class SettingCreate(SettingBase):
    id: str | None = None


class SettingUpdate(CamelModel):
    name: str | None = None
    type: str | None = None
    desc: str | None = None


class SettingRead(CamelModel):
    id: str
    name: str
    type: str
    desc: str
