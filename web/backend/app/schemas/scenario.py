"""Scenario request/response schemas (with the embedded ``Branch`` value type)."""

from __future__ import annotations

from pydantic import Field

from app.schemas.base import BranchTag, CamelModel


class Branch(CamelModel):
    label: str
    check: str = ""
    outcome: str = ""
    tag: BranchTag


class ScenarioBase(CamelModel):
    title: str
    genre: str = "Custom"
    tone: str = "Unset"
    goal: str = ""
    cast_ids: list[str] = Field(default_factory=list)
    setting_id: str = ""
    opening: str = ""
    branches: list[Branch] = Field(default_factory=list)
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
    image: str | None = None
    scene_art_positive: str | None = None
    scene_art_negative: str | None = None


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
