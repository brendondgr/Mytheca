"""Storyline request/response schemas.

``StorylineRead`` is a *summary* (no nested children) — the contract fetches
characters/settings/scenarios from their own per-storyline endpoints.
"""

from __future__ import annotations

from pydantic import Field, field_validator

from app.schemas.base import CamelModel


class StorylineBase(CamelModel):
    title: str = "Untitled Storyline"
    genre: str = "Uncharted"
    tagline: str | None = None
    premise: str | None = None
    # Agent-facing runtime context (distinct from the human-facing premise).
    world_primer: str | None = None
    # Customizable seal (shape glyph + hex color) shown left of the name.
    symbol: str = "◆"
    symbol_color: str = "#C8862A"
    # Per-storyline writing-prompt overrides ({registry key -> prompt text}).
    prompt_overrides: dict[str, str] = Field(default_factory=dict)


class StorylineCreate(StorylineBase):
    id: str | None = None


class StorylineUpdate(CamelModel):
    title: str | None = None
    genre: str | None = None
    tagline: str | None = None
    premise: str | None = None
    world_primer: str | None = None
    symbol: str | None = None
    symbol_color: str | None = None
    prompt_overrides: dict[str, str] | None = None


class StorylineRead(CamelModel):
    id: str
    title: str
    genre: str
    tagline: str | None = None
    premise: str | None = None
    world_primer: str | None = None
    symbol: str = "◆"
    symbol_color: str = "#C8862A"
    # Entity counts — populated by the list and single-get routes via SQL
    # subqueries so the switcher dropdown always shows accurate totals without
    # loading full child arrays. Defaults to 0 for create/update responses.
    scenario_count: int = 0
    character_count: int = 0
    setting_count: int = 0
    prompt_overrides: dict[str, str] = Field(default_factory=dict)

    @field_validator("prompt_overrides", mode="before")
    @classmethod
    def _coerce_overrides(cls, v: object) -> object:
        return v or {}


# ---- Authoring (the agent process of building a storyline) ------------------
# ``docsOverview`` is optional inline text read from dropped reference files in
# the browser and passed for *this generation only* — it is never persisted or
# indexed (retrieval/RAG is a later plan).


class StorylineDraftRequest(CamelModel):
    seed: str
    docs_overview: str | None = None


class StorylineDraftResponse(CamelModel):
    """Metadata drafted from a one-sentence seed (fills the create form)."""

    title: str = ""
    genre: str = ""
    tagline: str = ""
    premise: str = ""


class WorldPrimerRequest(CamelModel):
    premise: str | None = None
    seed: str | None = None
    docs_overview: str | None = None


class WorldPrimerResponse(CamelModel):
    world_primer: str
