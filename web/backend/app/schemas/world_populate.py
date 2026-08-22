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


class ExtractedEntity(CamelModel):
    """One subject a reference document explicitly names and profiles.

    ``source`` is a self-contained paragraph drawn strictly from that document — the
    downstream draft agent works from it without seeing the original file.
    """

    name: str
    source: str = ""


class ExtractedEntities(CamelModel):
    characters: list[ExtractedEntity] = []
    settings: list[ExtractedEntity] = []


class RosterEntry(CamelModel):
    """One cast member or place the build is going to make.

    Either invented (``seed`` — a one-line brief from the roster agent) or taken from
    one of the author's own documents (``source`` — the self-contained paragraph the
    extraction agent drew from ``doc_name``). ``doc_id`` is kept so the created entity
    can be linked back to the file it came from.
    """

    name: str
    seed: str = ""
    source: str = ""
    doc_id: str | None = None
    doc_name: str = ""


class RosterProposal(CamelModel):
    characters: list[RosterEntry] = []
    settings: list[RosterEntry] = []


# Where the roster comes from. ``documents`` builds exactly the characters and places
# the author's uploaded files name; ``invent`` makes them up from the premise;
# ``auto`` (the default) uses the documents when the world has any and only invents
# when it has none.
RosterSource = Literal["auto", "documents", "invent"]


class WorldPopulateRequest(CamelModel):
    """What to build. ``docs_overview`` is the author's Draft-selected file text."""

    docs_overview: str | None = None
    # Resume point: attach to a run already in flight and replay from this frame
    # onward. 0 (the default) is a fresh watch from the first frame.
    from_seq: int = 0
    source: RosterSource = "auto"
    max_characters: int = Field(default=DEFAULT_MAX_CHARACTERS, ge=0, le=MAX_CHARACTERS_CAP)
    max_settings: int = Field(default=DEFAULT_MAX_SETTINGS, ge=0, le=MAX_SETTINGS_CAP)
    # Artwork is opt-in and best-effort: every image is a ComfyUI render, so a run
    # with it on can take minutes and a failed render never fails its entity.
    with_artwork: bool = False
    #: Which look every image the build renders should wear (``app.content.art_styles``).
    #: Omitted = the operator's default from Options. A world build paints a whole cast and
    #: every place in one go, which makes it the surface where a *consistent* style matters
    #: most — so the choice is made once, up front, and applied to every render in the run.
    art_style: str | None = None


# ---- stream frames ----------------------------------------------------------

PopulateStage = Literal["roster", "character", "setting"]


class PopulateFrame(CamelModel):
    """Base for every populate frame.

    ``seq`` is the frame's position in the run's log, stamped by the run registry. The
    client echoes the last one it saw as ``fromSeq`` when it re-attaches, so a dropped
    connection resumes exactly where it left off. Keep-alive frames (emitted by the
    route, not the log) carry ``-1`` and are never resumed from.
    """

    seq: int = -1


class PopulatePlanFrame(PopulateFrame):
    """What the run is about to build, named, before it starts building it.

    Emitted once, after the roster is settled — so the author sees the cast list (and
    which of their files each name came from) rather than watching entities appear
    from nowhere.
    """

    type: Literal["plan"] = "plan"
    source: RosterSource
    characters: list[RosterEntry] = []
    settings: list[RosterEntry] = []
    # Documents read but naming nothing, and anything else worth saying up front.
    note: str = ""


class PopulateStatusFrame(PopulateFrame):
    """Progress heartbeat: which stage, and which item of how many."""

    type: Literal["status"] = "status"
    stage: PopulateStage
    message: str = ""
    name: str = ""
    index: int = 0
    total: int = 0


class PopulateEntityFrame(PopulateFrame):
    """One persisted entity — the proof the generated content reached the database."""

    type: Literal["entity"] = "entity"
    stage: Literal["character", "setting"]
    id: str
    name: str
    # The character's role, or the setting's type — enough for the build console to
    # show what landed without re-fetching the entity.
    role: str = ""
    image: str | None = None


class PopulateErrorFrame(PopulateFrame):
    """A non-fatal failure (one draft, one render) — the run continues after it."""

    type: Literal["error"] = "error"
    message: str
    fatal: bool = False


class PopulateDoneFrame(PopulateFrame):
    type: Literal["done"] = "done"
    characters: int = 0
    settings: int = 0


PopulateEvent = (
    PopulateStatusFrame
    | PopulatePlanFrame
    | PopulateEntityFrame
    | PopulateErrorFrame
    | PopulateDoneFrame
)
