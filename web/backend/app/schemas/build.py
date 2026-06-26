"""World-build schemas — the reviewable ``ProposedWorld`` the build agent returns.

The New Storyline page's **Build the whole world** action drafts everything at
once (text + the universal stat schema) and returns it for review; nothing is
persisted by the build call. The page commits the approved world via the normal
CRUD endpoints (and renders images then, if ComfyUI is configured). Proposed
characters/settings reuse the existing draft response shapes so the commit maps
straight onto ``CharacterCreate`` / ``SettingCreate``.
"""

from __future__ import annotations

from app.schemas.base import CamelModel
from app.schemas.character import CharacterDraftResponse
from app.schemas.setting import SettingDraftResponse
from app.schemas.stat import StatDefinitionBase

# Bounds so a single build stays affordable (one LLM call per entity).
MAX_CHARACTERS = 6
MAX_SETTINGS = 5
MAX_STATS = 8


class BuildWorldRequest(CamelModel):
    # At least one of seed / docsOverview is required (build from a sentence, from
    # dropped files, or both — the author need not "describe" the world by hand
    # when context files are provided).
    seed: str | None = None
    docs_overview: str | None = None
    storyline_id: str | None = None
    max_characters: int | None = None
    max_settings: int | None = None


class ProposedStoryline(CamelModel):
    title: str = ""
    genre: str = ""
    tagline: str = ""
    premise: str = ""
    world_primer: str = ""


class ProposedStat(StatDefinitionBase):
    """A proposed universal stat — same shape that ``POST /storylines/{id}/stats``
    persists (key/displayName/description/range/bands)."""


class ProposedStartingStat(CamelModel):
    key: str
    value: int


class ProposedCharacter(CharacterDraftResponse):
    """A drafted character + its proposed starting stat values (schema defaults)."""

    starting_stats: list[ProposedStartingStat] = []


class ProposedSetting(SettingDraftResponse):
    """A drafted setting (same fields the setting draft endpoint returns)."""


class ProposedWorld(CamelModel):
    storyline: ProposedStoryline
    stats: list[ProposedStat] = []
    characters: list[ProposedCharacter] = []
    settings: list[ProposedSetting] = []
