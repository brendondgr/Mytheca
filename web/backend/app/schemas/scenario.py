"""Scenario request/response schemas (with the embedded ``Branch`` value type)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from app.schemas.base import BeatLength, BranchTag, CamelModel


class Branch(CamelModel):
    label: str
    check: str = ""
    outcome: str = ""
    tag: BranchTag


class SceneVerb(CamelModel):
    """One of the scene's own direction verbs.

    ``label`` is the chip; ``text`` is the phrasing written into the direction box for the
    player to edit. They are deliberately separate — a verb exists to hand the player a
    sentence to argue with, not a command to fire, so a label repeated as its own text would
    miss the point.

    ``group`` is a ``Literal`` rather than a plain string so an unknown group is a 422 here
    rather than a verb that silently never renders, since the bar draws by group.
    """

    label: str = Field(min_length=1, max_length=40)
    group: Literal["pace", "tone", "event", "exit"] = "event"
    text: str = Field(min_length=1, max_length=400)


class ScenarioBase(CamelModel):
    title: str
    genre: str = "Custom"
    tone: str = "Unset"
    goal: str = ""
    cast_ids: list[str] = Field(default_factory=list)
    setting_id: str = ""
    opening: str = ""
    branches: list[Branch] = Field(default_factory=list)
    # Per-scene play controls: ``max_turns`` caps character replies per player message
    # (≥1); ``suggestions_count`` is how many follow-up suggestions to offer (0–4);
    # ``context_beats`` is the recent-transcript depth the character conditions on (5–100);
    # ``beat_length`` is how much a CHARACTER says in one beat (short 1–2 paragraphs,
    # medium 2–4, long 5–6). A ``Literal`` rather than a plain str so an unknown tier is a
    # 422 here rather than a silently-ignored value reaching the prompt builder — the same
    # reason ``context_beats`` is clamped at this boundary rather than downstream.
    max_turns: int = Field(default=5, ge=1)
    suggestions_count: int = Field(default=4, ge=0, le=4)
    context_beats: int = Field(default=14, ge=5, le=100)
    beat_length: BeatLength = "medium"
    # Per-scenario writing-prompt overrides ({registry key -> prompt text}) — override the
    # storyline's prompts for this scene only.
    prompt_overrides: dict[str, str] = Field(default_factory=dict)
    # The scene's own one-tap direction verbs, appended to the built-in bar's groups. Capped
    # because the bar is a glance-and-tap surface: past a handful it becomes the wall of
    # buttons the grouping exists to avoid.
    direction_verbs: list[SceneVerb] = Field(default_factory=list, max_length=8)
    # Optional scene art — persisted when the author renders an image via ComfyUI.
    image: str | None = None
    scene_art_positive: str | None = None
    scene_art_negative: str | None = None


class ScenarioCreate(ScenarioBase):
    id: str | None = None


class ScenarioUpdate(CamelModel):
    title: str | None = None
    genre: str | None = None
    tone: str | None = None
    goal: str | None = None
    cast_ids: list[str] | None = None
    setting_id: str | None = None
    opening: str | None = None
    branches: list[Branch] | None = None
    max_turns: int | None = Field(default=None, ge=1)
    suggestions_count: int | None = Field(default=None, ge=0, le=4)
    context_beats: int | None = Field(default=None, ge=5, le=100)
    beat_length: BeatLength | None = None
    direction_verbs: list[SceneVerb] | None = Field(default=None, max_length=8)
    prompt_overrides: dict[str, str] | None = None
    image: str | None = None
    scene_art_positive: str | None = None
    scene_art_negative: str | None = None


class ScenarioRead(CamelModel):
    id: str
    title: str
    genre: str
    tone: str
    goal: str
    cast_ids: list[str]
    setting_id: str
    opening: str
    branches: list[Branch]
    max_turns: int = 5
    suggestions_count: int = 4
    context_beats: int = 14
    beat_length: BeatLength = "medium"
    direction_verbs: list[SceneVerb] = Field(default_factory=list)
    prompt_overrides: dict[str, str] = Field(default_factory=dict)
    image: str | None = None
    scene_art_positive: str | None = None
    scene_art_negative: str | None = None

    @field_validator("prompt_overrides", mode="before")
    @classmethod
    def _coerce_overrides(cls, v: object) -> object:
        return v or {}

    @field_validator("direction_verbs", mode="before")
    @classmethod
    def _coerce_verbs(cls, v: object) -> object:
        # The column is nullable, so an older row reads as None. Empty list, not a 422.
        return v or []


# ---- Authoring (the agentic Scenario Creator) -------------------------------
# A scenario drafted from a one-line seed. The agent picks a *valid* cast and
# setting grounded in the active world's real roster: it returns names chosen
# from a numbered roster, which the agent resolves to ids server-side, dropping
# anything that doesn't match (so the draft never invents or dangles a reference).


class ScenarioDraftRequest(CamelModel):
    seed: str
    docs_overview: str | None = None
    storyline_id: str | None = None


class ScenarioDraftResponse(CamelModel):
    title: str = ""
    genre: str = ""
    tone: str = ""
    goal: str = ""
    opening: str = ""
    cast_ids: list[str] = Field(default_factory=list)
    setting_id: str = ""


# ---- the Story-Graph read on scenario load (§7.2) ---------------------------
# Returned by GET /scenarios/{id}/graph: the cast + setting subgraph read live
# from Neo4j. ``available`` is False (empty lists) when the graph is off/unreachable.


class GraphNodeRead(CamelModel):
    id: str
    type: str | None = None
    label: str | None = None
    storyline: str | None = None
    metadata: dict = Field(default_factory=dict)


class GraphEdgeRead(CamelModel):
    source: str
    target: str
    type: str
    metadata: dict = Field(default_factory=dict)


class ScenarioGraphRead(CamelModel):
    available: bool
    scenario_id: str
    nodes: list[GraphNodeRead] = Field(default_factory=list)
    edges: list[GraphEdgeRead] = Field(default_factory=list)


# ---- Scene-art authoring (the agentic Scenario Scene Art creator) ------------
# Reuse ``SceneArtPromptResponse`` / ``SceneArtGenerateResponse`` from
# ``app.schemas.setting`` — they have the exact same shape.


class ScenarioSceneArtPromptRequest(CamelModel):
    """The scenario context the scene-art prompts should depict."""

    title: str = ""
    genre: str | None = None
    tone: str | None = None
    goal: str | None = None
    opening: str | None = None
    # Resolved setting context (passed by the frontend from the active world).
    setting_name: str | None = None
    setting_desc: str | None = None
    notes: str | None = None
