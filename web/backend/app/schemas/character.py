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


# ---- Authoring (the agentic Character Creator) ------------------------------
# The agent fills a character's *base identity* (§1 node properties) — never the
# graph. ``docsOverview`` is inline text from dropped reference files, passed for a
# single generation only (never persisted/indexed; RAG is a later plan).


class CharacterDraftRequest(CamelModel):
    seed: str
    docs_overview: str | None = None
    # Optional: ground the draft in a specific world (its primer/genre).
    storyline_id: str | None = None


class CharacterDraftResponse(CamelModel):
    """A character drafted from a seed: the by-hand fields + base-identity prose."""

    name: str = ""
    role: str = ""
    traits: str = ""
    speech: str = ""
    goal: str = ""
    secret: str = ""
    appearance: str = ""
    background: str = ""
    personality: str = ""
    # A suggested accent color (hex); the UI may keep or override it.
    color: str = ""


class PortraitPromptRequest(CamelModel):
    """The character description the portrait prompts should depict."""

    name: str = ""
    role: str | None = None
    appearance: str | None = None
    traits: str | None = None
    personality: str | None = None
    # Optional explicit hints (the model also infers species/race from the prose).
    species: str | None = None
    notes: str | None = None


class PortraitPromptResponse(CamelModel):
    """Comma-separated ComfyUI prompts for the watercolor portrait pipeline."""

    positive: str = ""
    negative: str = ""


class StartingStatProposal(CamelModel):
    key: str
    display_name: str
    value: int
    min: int
    max: int
    rationale: str = ""


class StartingStatsRequest(CamelModel):
    storyline_id: str
    name: str = ""
    role: str | None = None
    traits: str | None = None
    personality: str | None = None
    background: str | None = None


class StartingStatsResponse(CamelModel):
    """Proposed starting values, keyed to the storyline's stat definitions."""

    proposals: list[StartingStatProposal] = []
