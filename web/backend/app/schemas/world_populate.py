"""World-population schemas — the roster proposal + the populate NDJSON frames.

Population is the create-time phase that turns an empty new world into one with a
cast and places: ``agents.roster_agent`` proposes the roster (names + one-line
seeds), ``services.world_populate`` drafts and persists each entry, and the route
streams the frames below so the author watches it happen.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.base import CamelModel

# Bounds on a single run. Defaults keep a run finite (and a local reasoning model's
# budget sane); the caps are the hard ceiling the request is clamped to.
DEFAULT_MAX_CHARACTERS = 5
DEFAULT_MAX_SETTINGS = 3
MAX_CHARACTERS_CAP = 8
MAX_SETTINGS_CAP = 6


class RosterEntry(CamelModel):
    """One proposed cast member or place: a name plus the seed line drafting uses."""

    name: str
    seed: str = ""


class RosterProposal(CamelModel):
    characters: list[RosterEntry] = []
    settings: list[RosterEntry] = []


class WorldPopulateRequest(CamelModel):
    """What to build. ``docs_overview`` is the author's Draft-selected file text."""

    docs_overview: str | None = None
    max_characters: int = Field(default=DEFAULT_MAX_CHARACTERS, ge=0, le=MAX_CHARACTERS_CAP)
    max_settings: int = Field(default=DEFAULT_MAX_SETTINGS, ge=0, le=MAX_SETTINGS_CAP)
    # Artwork is opt-in and best-effort: every image is a ComfyUI render, so a run
    # with it on can take minutes and a failed render never fails its entity.
    with_artwork: bool = False


# ---- stream frames ----------------------------------------------------------

PopulateStage = Literal["roster", "character", "setting"]


class PopulateStatusFrame(CamelModel):
    """Progress heartbeat: which stage, and which item of how many."""

    type: Literal["status"] = "status"
    stage: PopulateStage
    message: str = ""
    name: str = ""
    index: int = 0
    total: int = 0


class PopulateEntityFrame(CamelModel):
    """One persisted entity — the proof the generated content reached the database."""

    type: Literal["entity"] = "entity"
    stage: Literal["character", "setting"]
    id: str
    name: str
    image: str | None = None


class PopulateErrorFrame(CamelModel):
    """A non-fatal failure (one draft, one render) — the run continues after it."""

    type: Literal["error"] = "error"
    message: str
    fatal: bool = False


class PopulateDoneFrame(CamelModel):
    type: Literal["done"] = "done"
    characters: int = 0
    settings: int = 0


PopulateEvent = (
    PopulateStatusFrame | PopulateEntityFrame | PopulateErrorFrame | PopulateDoneFrame
)
