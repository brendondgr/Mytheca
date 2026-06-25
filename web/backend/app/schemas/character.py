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
    # Base-identity prose (authored once; the agentic creator fills these). Stored
    # as nullable columns — §1 node properties, not graph structure.
    appearance: str | None = None
    background: str | None = None
    personality: str | None = None
    # Relative URL (/media/...) of the generated WebP portrait, or None.
    portrait: str | None = None


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
    appearance: str | None = None
    background: str | None = None
    personality: str | None = None
    portrait: str | None = None


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
    appearance: str | None = None
    background: str | None = None
    personality: str | None = None
    portrait: str | None = None
