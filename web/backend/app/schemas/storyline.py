"""Storyline request/response schemas.

``StorylineRead`` is a *summary* (no nested children) — the contract fetches
characters/settings/scenarios from their own per-storyline endpoints.
"""

from __future__ import annotations

from app.schemas.base import CamelModel


class StorylineBase(CamelModel):
    title: str = "Untitled Storyline"
    genre: str = "Uncharted"
    tagline: str | None = None


class StorylineCreate(StorylineBase):
    id: str | None = None


class StorylineUpdate(CamelModel):
    title: str | None = None
    genre: str | None = None
    tagline: str | None = None


class StorylineRead(CamelModel):
    id: str
    title: str
    genre: str
    tagline: str | None = None
