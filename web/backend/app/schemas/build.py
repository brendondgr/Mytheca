"""World-build schemas — the reviewable ``ProposedWorld`` the build agent returns.

The New Storyline page's **Build the whole world** action drafts everything at
once (text + the universal stat schema) and returns it for review; nothing is
persisted by the build call. The page commits the approved world via the normal
CRUD endpoints (and renders images then, if ComfyUI is configured). Proposed
characters/settings reuse the existing draft response shapes so the commit maps
straight onto ``CharacterCreate`` / ``SettingCreate``.
"""

from __future__ import annotations

from typing import Literal

from app.schemas.base import CamelModel
from app.schemas.character import CharacterDraftResponse, VoiceSample
from app.schemas.setting import SettingDraftResponse
from app.schemas.stat import StatDefinitionBase

# Bounds so a single build stays affordable (one LLM call per entity).
MAX_CHARACTERS = 6
MAX_SETTINGS = 5
MAX_STATS = 8


class BuildDoc(CamelModel):
    """An attached reference document that MAY be mined for characters / settings.

    A doc may describe ONE subject or MANY (a roster, a mixed scene, general lore).
    Extraction is **opt-in per document**: only a doc with ``extract=True`` is fed
    into the extraction pass — the author checks **Extract** on the files they want
    turned into cast/settings. ``category`` is the author's triage bucket, which then
    scopes *what kind* is mined (character/setting/uncategorized); ``extract`` gates
    *whether* the doc is mined at all (default OFF — a new storyline never auto-mines).
    """

    name: str = ""
    text: str = ""
    category: str | None = None
    # Opt-in gate: mine this doc for named characters/settings during the build.
    extract: bool = False


class ExtractedEntity(CamelModel):
    """One distinct subject found inside a document by the extraction agent.

    ``name`` labels the skeleton card; ``source`` is a focused brief for that single
    subject, handed to ``draft_character`` / ``draft_setting`` to flesh out.
    """

    name: str = ""
    source: str = ""


class ExtractedEntities(CamelModel):
    """The characters + settings the extraction agent found in one document."""

    characters: list[ExtractedEntity] = []
    settings: list[ExtractedEntity] = []


class BuildWorldRequest(CamelModel):
    # At least one of seed / docsOverview is required (build from a sentence, from
    # dropped files, or both — the author need not "describe" the world by hand
    # when context files are provided).
    seed: str | None = None
    docs_overview: str | None = None
    storyline_id: str | None = None
    max_characters: int | None = None
    max_settings: int | None = None
    # Attached, triaged reference docs, split by the author's classification. Extraction
    # RESPECTS the bucket (it never invents a subject by expanding lore):
    #   - character_docs     → mine for explicitly NAMED characters only (usually one;
    #                          split only if it clearly names several; a doc with no
    #                          named subject still becomes ONE character — the
    #                          classification asserts it is one).
    #   - setting_docs       → the same, for named settings.
    #   - uncategorized_docs → produce an entity ONLY if a genuinely NAMED character /
    #                          setting is present; lore/history/rules/atmosphere →
    #                          nothing.
    #   - other_docs         → LORE/GROUNDING ONLY — never become entities (they fold
    #                          into the drafting grounding so drafts stay consistent).
    # The build never invents an entity from thin air — with no entity docs, no cast.
    character_docs: list[BuildDoc] = []
    setting_docs: list[BuildDoc] = []
    uncategorized_docs: list[BuildDoc] = []
    other_docs: list[BuildDoc] = []


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
    """A drafted character + its voice profile and proposed starting stat values.

    Voice & tone samples are derived from the drafted background/personality *before*
    the (schema-default) starting stats, so voice comes first. Both map straight onto
    ``CharacterCreate`` at commit time.
    """

    voice_samples: list[VoiceSample] = []
    starting_stats: list[ProposedStartingStat] = []


class ProposedSetting(SettingDraftResponse):
    """A drafted setting (same fields the setting draft endpoint returns)."""


class ProposedWorld(CamelModel):
    storyline: ProposedStoryline
    stats: list[ProposedStat] = []
    characters: list[ProposedCharacter] = []
    settings: list[ProposedSetting] = []


# ---- Live build stream (NDJSON) --------------------------------------------
#
# The streaming build endpoint (``POST /storylines/build/stream``) emits one of
# these JSON objects per line (``application/x-ndjson``) as the world is drafted,
# so the New Storyline page can render the title/genre/premier, the cast, and the
# settings *as they are built* instead of waiting for the whole proposal. The
# non-streaming ``/build`` route still returns a single ``ProposedWorld`` (the
# collector over the same generator), so both contracts coexist.


class BuildStatusEvent(CamelModel):
    """A human-readable stage marker (drive the progress line / spinner)."""

    type: Literal["status"] = "status"
    stage: str
    message: str


class BuildMetaEvent(CamelModel):
    """Storyline metadata is drafted — fill the Title/Genre/Tagline/Premise."""

    type: Literal["meta"] = "meta"
    title: str = ""
    genre: str = ""
    tagline: str = ""
    premise: str = ""


class BuildPrimerEvent(CamelModel):
    """The World Primer is written."""

    type: Literal["primer"] = "primer"
    world_primer: str = ""


class BuildPlanEvent(CamelModel):
    """The blueprint is ready: the stat schema + the cast/setting concept list.

    The ``characters``/``settings`` here are one-sentence *concepts* (not full
    drafts) — enough for the UI to render skeleton cards that fill in as each
    ``character``/``setting`` event arrives.
    """

    type: Literal["plan"] = "plan"
    stats: list[ProposedStat] = []
    characters: list[str] = []
    settings: list[str] = []


class BuildCharacterEvent(CamelModel):
    """One character finished drafting (slots into the skeleton at ``index``)."""

    type: Literal["character"] = "character"
    index: int
    total: int
    character: ProposedCharacter


class BuildSettingEvent(CamelModel):
    """One setting finished drafting (slots into the skeleton at ``index``)."""

    type: Literal["setting"] = "setting"
    index: int
    total: int
    setting: ProposedSetting


class BuildDoneEvent(CamelModel):
    """Terminal success event — carries the assembled ``ProposedWorld``."""

    type: Literal["done"] = "done"
    world: ProposedWorld


class BuildErrorEvent(CamelModel):
    """Terminal error event — emitted in-band once the 200 stream has opened."""

    type: Literal["error"] = "error"
    message: str


BuildEvent = (
    BuildStatusEvent
    | BuildMetaEvent
    | BuildPrimerEvent
    | BuildPlanEvent
    | BuildCharacterEvent
    | BuildSettingEvent
    | BuildDoneEvent
    | BuildErrorEvent
)
