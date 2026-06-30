"""Setting request/response schemas. ``SettingRead`` mirrors the frontend type."""

from __future__ import annotations

from pydantic import field_validator

from app.schemas.base import CamelModel


class SettingTimelineEntry(CamelModel):
    """One durable thing that happened at a place (§4.1 event timeline).

    Play-accrued by the async worker; never authored at creation. Kept loose so the
    later graph writer can populate it without a schema change.
    """

    summary: str = ""
    origin: dict | None = None  # {scenario, turn}
    participants: list[str] = []
    kind: str = ""
    visibility: str = "public"


class SettingBase(CamelModel):
    name: str
    type: str = "Social Hub"
    desc: str = "A place yet to be described."
    # Setting Node metadata (§4.1) — authored base description + initial state.
    atmosphere: str | None = None
    features: str | None = None
    current_state: str | None = None
    # Optional establishing image: relative /media/... URL of the saved WebP.
    image: str | None = None
    # The ComfyUI prompts that produced the establishing image (persisted for re-edit).
    scene_art_positive: str | None = None
    scene_art_negative: str | None = None
    # Append-only event timeline; empty at authoring, accrues from play.
    timeline: list[SettingTimelineEntry] | None = None


class SettingCreate(SettingBase):
    id: str | None = None


class SettingUpdate(CamelModel):
    name: str | None = None
    type: str | None = None
    desc: str | None = None
    atmosphere: str | None = None
    features: str | None = None
    current_state: str | None = None
    image: str | None = None
    scene_art_positive: str | None = None
    scene_art_negative: str | None = None
    timeline: list[SettingTimelineEntry] | None = None


class SettingRead(CamelModel):
    id: str
    name: str
    type: str
    desc: str
    atmosphere: str | None = None
    features: str | None = None
    current_state: str | None = None
    image: str | None = None
    scene_art_positive: str | None = None
    scene_art_negative: str | None = None
    timeline: list[SettingTimelineEntry] = []

    @field_validator("timeline", mode="before")
    @classmethod
    def _coerce_timeline(cls, value: object) -> object:
        # Reconciled-but-unbackfilled rows (and the nullable column default) can be
        # NULL; the timeline reads as an empty log rather than failing validation.
        return value if value is not None else []


# ---- Authoring (the agentic Setting Creator) --------------------------------
# The agent fills a setting's *base description + current state* (§4.1 node
# properties) — never the timeline (play-accrued) and never edges (graph). The
# optional establishing image reuses the ComfyUI pipeline. ``docsOverview`` is
# inline text from dropped reference files, passed for a single generation only
# (never persisted/indexed; RAG is a later plan).


class SettingDraftRequest(CamelModel):
    seed: str
    docs_overview: str | None = None
    # Optional: ground the draft in a specific world (its primer/genre).
    storyline_id: str | None = None


class SettingDraftResponse(CamelModel):
    """A setting drafted from a seed: the by-hand fields + base-description prose."""

    name: str = ""
    type: str = ""
    desc: str = ""
    atmosphere: str = ""
    features: str = ""
    current_state: str = ""


class SceneArtPromptRequest(CamelModel):
    """The place description the scene-art prompts should depict."""

    name: str = ""
    type: str | None = None
    desc: str | None = None
    atmosphere: str | None = None
    features: str | None = None
    current_state: str | None = None
    notes: str | None = None


class SceneArtPromptResponse(CamelModel):
    """Comma-separated ComfyUI prompts for the watercolor establishing shot."""

    positive: str = ""
    negative: str = ""


class SceneArtGenerateRequest(CamelModel):
    """Render a watercolor establishing image via ComfyUI from the given prompts.

    Id-agnostic: the resulting ``/media/...`` URL is carried into the normal
    setting create/update payload (works during creation, before a row exists).
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


class SceneArtGenerateResponse(CamelModel):
    image: str  # relative /media/scenes/... URL of the saved WebP
