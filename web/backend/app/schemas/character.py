"""Character request/response schemas. ``CharacterRead`` mirrors the frontend type."""

from __future__ import annotations

from pydantic import Field, field_validator

from app.schemas.base import CamelModel

# The kinds of moment a voice sample may be tagged with — the same axis
# ``planner_agent`` reads per beat as a beat's ``register``. The field is called
# ``moment`` rather than ``register`` because a pydantic field named ``register``
# shadows ``ABCMeta.register`` on the model base. Empty (untagged) means "any moment".
VOICE_MOMENTS = ("light", "neutral", "tense", "grave")


class VoiceSample(CamelModel):
    """One situation → single-response pair defining how a character speaks.

    ``situation`` is a previous situation the character was confronted with —
    often another character's line of dialogue; ``sample`` is the character's
    single in-voice response to that situation (one turn, never a back-and-forth
    exchange), reacting to what specifically happened rather than restating a
    generic description of their voice.

    ``moment`` tags which kind of moment the pair demonstrates — ``light`` ·
    ``neutral`` · ``tense`` · ``grave``, matching ``planner_agent``'s per-beat
    ``register``. Only the pairs matching the current beat (plus untagged ones) are
    injected, so a character has a concrete exemplar of themselves *not at rest*
    instead of always being shown their baseline voice. Empty means "any moment";
    anything unrecognized is coerced to empty rather than rejected, since these rows
    are free-form JSON that predate the field.
    """

    situation: str = ""
    sample: str = ""
    moment: str = ""

    @field_validator("moment", mode="before")
    @classmethod
    def _coerce_moment(cls, value: object) -> str:
        text = str(value or "").strip().lower()
        return text if text in VOICE_MOMENTS else ""


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
    # The ComfyUI prompts that produced the portrait (persisted for re-edit).
    portrait_positive: str | None = None
    portrait_negative: str | None = None
    # Voice & tone profile: situation → sample-response pairs (see ``VoiceSample``).
    voice_samples: list[VoiceSample] | None = None
    # A bias on top of the beat's register, `[-2, +2]`, `None` = neutral. Bounded here so an
    # out-of-range value is a 422 rather than a silently-clamped surprise downstream.
    looseness: int | None = Field(default=None, ge=-2, le=2)


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
    portrait_positive: str | None = None
    portrait_negative: str | None = None
    voice_samples: list[VoiceSample] | None = None
    looseness: int | None = Field(default=None, ge=-2, le=2)


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
    portrait_positive: str | None = None
    portrait_negative: str | None = None
    voice_samples: list[VoiceSample] = []
    looseness: int | None = None

    @field_validator("voice_samples", mode="before")
    @classmethod
    def _coerce_voice_samples(cls, value: object) -> object:
        # Reconciled-but-unbackfilled rows (and the nullable column default) can be
        # NULL; the profile reads as an empty list rather than failing validation.
        return value if value is not None else []


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


class PortraitGenerateRequest(CamelModel):
    """Render a watercolor portrait via ComfyUI from the given prompts.

    Id-agnostic: the resulting ``/media/...`` URL is carried into the normal
    character create/update payload (works during creation, before a row exists).
    Optional overrides fall back to the configured ComfyUI workflow/params.
    """

    positive: str
    negative: str | None = None
    base_url: str | None = None
    workflow: str | None = None
    width: int | None = None
    height: int | None = None
    steps: int | None = None
    cfg: float | None = None


class PortraitGenerateResponse(CamelModel):
    portrait: str  # relative /media/... URL of the saved WebP


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


class VoiceSamplesRequest(CamelModel):
    """The character description a voice/tone profile should be derived from.

    Grounded in the drafted background/personality (and optionally the world) so the
    samples match tone and voice. Runs *before* starting stats — voice comes first.
    """

    name: str = ""
    role: str | None = None
    traits: str | None = None
    speech: str | None = None
    background: str | None = None
    personality: str | None = None
    storyline_id: str | None = None


class VoiceSamplesResponse(CamelModel):
    """Proposed situation → sample-response pairs (proposal only; caller applies)."""

    samples: list[VoiceSample] = []
