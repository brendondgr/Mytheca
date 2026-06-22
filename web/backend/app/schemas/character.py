"""Character request/response schemas. ``CharacterRead`` mirrors the frontend type."""

from __future__ import annotations

from app.schemas.base import CamelModel


class CharacterBase(CamelModel):
    name: str
    role: str = "Character"
    color: str = "#8E2B1C"
    traits: str = ""
    speech: str = ""
    goal: str = ""
    secret: str = ""


class CharacterCreate(CharacterBase):
    id: str | None = None
    # Derived from `name` by the service when omitted.
    mono: str | None = None


class CharacterUpdate(CamelModel):
    name: str | None = None
    role: str | None = None
    color: str | None = None
    mono: str | None = None
    traits: str | None = None
    speech: str | None = None
    goal: str | None = None
    secret: str | None = None


class CharacterRead(CamelModel):
    id: str
    name: str
    role: str
    color: str
    mono: str
    traits: str
    speech: str
    goal: str
    secret: str
