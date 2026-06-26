"""Setting authoring agent — the agentic Setting Creator (prep phase).

Two creation-time operations run over the configured LLM (same proxy + settings
store resolution as the storyline/character agents, via ``agents._common``):

* ``draft_setting`` — turn a one-sentence seed (optionally grounded in dropped
  reference docs and the active world) into a full setting draft: the by-hand
  fields (name / type / desc) plus the §4.1 node metadata
  (atmosphere / features / current_state).
* ``generate_scene_art_prompts`` — turn a place description into the
  positive/negative prompts for the watercolor ComfyUI establishing shot.

Everything produced here is a setting's *own* base description + current state
(§4.1 *node properties* of ``Documents/Plans/4.story-graph-structure-prep.md``) —
never graph structure. No edges, no Event/Faction nodes, no Neo4j, and never the
event timeline (that is play-accrued by the async worker once play exists).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents._common import (
    DEFAULT_AUTHORING_EFFORT,
    docs_block,
    extract_json,
    gen_params,
    resolve_llm,
    world_context,
)
from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.schemas.setting import SceneArtPromptResponse, SettingDraftResponse
from app.services import llm

# Canonical setting-type labels (mirrors the frontend ``SETTING_TYPES``). The
# value is stored verbatim, so a label off this list still persists — the chips
# just won't pre-highlight.
_SETTING_TYPES = "Social Hub, Exploration, Fortress, Black Market, Sacred, Wilderness"

_DRAFT_SYSTEM = (
    "You are Velora's setting-creation assistant. Given a short description of a "
    "place for an interactive-fiction world, flesh it out as a location the story "
    "will return to. Respond with ONLY a JSON object — no prose, no markdown, no "
    'code fences — with exactly these string keys: "name" (an evocative place '
    f'name), "type" (choose the single best fit from: {_SETTING_TYPES}), "desc" (one '
    'vivid line — the place in a breath, for a card), "atmosphere" (2-3 sentences '
    "of sensory character: sights, sounds, smells, light, texture — what it FEELS "
    'like to stand here), "features" (2-3 sentences naming notable physical '
    "features, fixtures, and points of interest a scene could use), and "
    '"currentState" (1-2 sentences on the initial here-and-now: time of day, '
    "weather, lighting, what is open or barred). Keep it consistent with any world "
    "context provided. Include no other keys."
)

_SCENE_ART_SYSTEM = (
    "You are Velora's scene-art-prompt writer for a watercolor image model "
    "(Z-Image-Turbo via ComfyUI). The model responds best to SHORT phrases "
    "separated by commas — not sentences. Given a place description, write the "
    "prompts for an atmospheric establishing shot of the LOCATION ITSELF — a vista "
    "or interior with NO people as the subject. Respond with ONLY a JSON object — "
    'no prose, no fences — with exactly two string keys: "positive" and "negative".'
    "\npositive: 10-16 short comma-separated phrases. Lead with the place and its "
    "kind (e.g. 'fog-bound harbor at dawn', 'smoke-dark dockside tavern interior', "
    "'flooded stone undercroft'), then its salient features, materials, light, "
    "weather, and mood. End with style tags: 'watercolor, soft washes, painterly, "
    "atmospheric, establishing shot, wide view, no people, detailed environment'.\n"
    "negative: a comma-separated list of what to avoid, e.g. 'people, figures, "
    "portrait, photorealistic, 3d render, text, watermark, signature, blurry, "
    "lowres'. Keep both prompts concise."
)


def draft_setting(
    db: Session,
    seed: str,
    docs_overview: str | None = None,
    storyline_id: str | None = None,
    *,
    reasoning: ReasoningEffort = DEFAULT_AUTHORING_EFFORT,
) -> SettingDraftResponse:
    """Draft a full setting (by-hand fields + §4.1 node metadata) from a seed."""
    seed = (seed or "").strip()
    if not seed:
        raise APIError(400, "bad_request", "Describe the place in a sentence to draft it.")
    base_url, api_key, model, params = resolve_llm(db)
    user = f"Setting seed: {seed}{world_context(db, storyline_id)}{docs_block(docs_overview)}"
    messages = [
        {"role": "system", "content": _DRAFT_SYSTEM},
        {"role": "user", "content": user},
    ]
    data = extract_json(
        llm.chat_complete(
            base_url, api_key, model, messages, gen_params(params), reasoning=reasoning
        )
    )

    def _s(key: str) -> str:
        return str(data.get(key) or "").strip()

    return SettingDraftResponse(
        name=_s("name"),
        type=_s("type"),
        desc=_s("desc"),
        atmosphere=_s("atmosphere"),
        features=_s("features"),
        current_state=_s("currentState"),
    )


def generate_scene_art_prompts(
    db: Session,
    *,
    name: str = "",
    type: str | None = None,
    desc: str | None = None,
    atmosphere: str | None = None,
    features: str | None = None,
    current_state: str | None = None,
    notes: str | None = None,
    reasoning: ReasoningEffort = DEFAULT_AUTHORING_EFFORT,
) -> SceneArtPromptResponse:
    """Write the watercolor positive/negative ComfyUI prompts for a place."""
    fields = {
        "Name": name,
        "Type": type,
        "Description": desc,
        "Atmosphere": atmosphere,
        "Features": features,
        "Current state": current_state,
        "Notes": notes,
    }
    described = "\n".join(f"{k}: {v}".strip() for k, v in fields.items() if (v or "").strip())
    if not described:
        raise APIError(
            400, "bad_request", "Describe the place (at least a name or atmosphere) first."
        )
    base_url, api_key, model, params = resolve_llm(db)
    messages = [
        {"role": "system", "content": _SCENE_ART_SYSTEM},
        {"role": "user", "content": f"Place:\n{described}"},
    ]
    data = extract_json(
        llm.chat_complete(
            base_url, api_key, model, messages, gen_params(params), reasoning=reasoning
        )
    )
    return SceneArtPromptResponse(
        positive=str(data.get("positive") or "").strip(),
        negative=str(data.get("negative") or "").strip(),
    )
