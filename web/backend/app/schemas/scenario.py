"""Scenario request/response schemas (with the embedded ``Branch`` value type)."""

from __future__ import annotations

from pydantic import Field

from app.schemas.base import BranchTag, CamelModel


class Branch(CamelModel):
    label: str
    check: str = ""
    outcome: str = ""
    tag: BranchTag


class ScenarioBase(CamelModel):
    title: str
    genre: str = "Custom"
    tone: str = "Unset"
    goal: str = ""
    cast_ids: list[str] = Field(default_factory=list)
    setting_id: str = ""
    opening: str = ""
    branches: list[Branch] = Field(default_factory=list)


class ScenarioCreate(ScenarioBase):
    id: str | None = None


class ScenarioUpdate(CamelModel):
    title: str | None = None
    genre: str | None = None
    tone: str | None = None
    goal: str | None = None
    cast_ids: list[str] | None = None
    setting_id: str | None = None
    opening: str | None = None
    branches: list[Branch] | None = None


class ScenarioRead(CamelModel):
    id: str
    title: str
    genre: str
    tone: str
    goal: str
    cast_ids: list[str]
    setting_id: str
    opening: str
    branches: list[Branch]
