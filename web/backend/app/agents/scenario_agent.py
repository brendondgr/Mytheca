"""Scenario authoring agent — the agentic Scenario Creator.

``draft_scenario`` turns a one-sentence scene seed into a full scenario draft:
the by-hand fields (title / genre / tone / goal / opening) plus a **valid** cast
and setting chosen from the active world's real roster.

The agent never trusts model-emitted ids. It hands the model a numbered roster of
the characters and settings that actually exist in the storyline and asks it to
return **names** drawn only from those lists; we resolve names → ids in Python and
**drop anything that doesn't match** (and fall back to ``""`` for a missing
setting). This mirrors how the world build keeps cast/settings grounded to real
inputs and honors the "``setting_id`` is a soft reference, fall back gracefully"
rule on the read side.

Grounding is shared with the character/setting agents via ``agents._common``
(``world_context`` / ``docs_block``) — one grounding path, no bespoke code. No
graph, no persistence: the draft is returned for review and only saved through the
normal scenario CRUD when the author commits.
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
from app.schemas.scenario import ScenarioDraftResponse
from app.schemas.setting import SceneArtPromptResponse
from app.services import crud, llm

_SCENE_ART_SYSTEM = (
    "You are Velora's scene-art-prompt writer for a watercolor image model "
    "(Z-Image-Turbo via ComfyUI). The model responds best to SHORT phrases "
    "separated by commas — not sentences. Given a scenario description, write the "
    "prompts for an atmospheric establishing shot of the SETTING as it appears in "
    "this specific scene moment — a vista or interior shaped by the scenario's tone "
    "and atmosphere, with NO people as the subject. Respond with ONLY a JSON object "
    '— no prose, no fences — with exactly two string keys: "positive" and "negative".'
    "\npositive: 10-16 short comma-separated phrases. Lead with the setting name and "
    "its kind (e.g. 'fog-bound harbor at dawn', 'candlelit merchant hall, tense "
    "atmosphere'), then the scene's lighting and time-of-day (drawn from the tone "
    "and opening), its salient features, and the emotional atmosphere matching the "
    "tone. End with style tags: 'watercolor, soft washes, painterly, atmospheric, "
    "establishing shot, wide view, no people, detailed environment'.\n"
    "negative: a comma-separated list of what to avoid, e.g. 'people, figures, "
    "portrait, photorealistic, 3d render, text, watermark, signature, blurry, "
    "lowres'. Keep both prompts concise."
)

# Bound the roster passed to the model so a very large world keeps the prompt in
# check (the same discipline as ``_common.DOCS_CAP``). ``list_characters`` /
# ``list_settings`` already order by (position, name), so this takes the most
# salient entries first. Refine if a world outgrows it.
_ROSTER_CAP = 40

_DRAFT_SYSTEM = (
    "You are Velora's scenario-creation assistant. Given a short scene seed for an "
    "interactive-fiction world, assemble the present-moment 'truth object' for that "
    "scene. You are given a numbered ROSTER of the characters and settings that "
    "exist in this world; you MUST choose the cast and setting only from that "
    "roster, by their exact names. Respond with ONLY a JSON object — no prose, no "
    "markdown, no code fences — with exactly these keys: "
    '"title" (an evocative scene title), "genre" (a short label, e.g. Intrigue), '
    '"tone" (a few words, e.g. "Tension · rising"), "goal" (one line: what is at '
    'stake in this scene), "opening" (2-4 sentences of narrator-voice scene-setting '
    'prose to open on), "cast" (an array of character NAMES copied exactly from the '
    'roster — the people present in this scene), and "setting" (ONE setting name '
    "copied exactly from the roster — where the scene takes place). Pick a cast and "
    "setting that fit the seed and the world. Use only names that appear in the "
    "roster; do not invent characters or places. Include no other keys."
)


def _roster_block(db: Session, storyline_id: str | None) -> tuple[str, dict[str, str], dict[str, str]]:
    """Render the world's cast + settings as a numbered roster for the prompt.

    Returns the prompt block plus two normalized name→id lookups (characters and
    settings) used to resolve the model's chosen names back to real ids.
    """
    if not storyline_id:
        return "", {}, {}
    try:
        characters = crud.list_characters(db, storyline_id)[:_ROSTER_CAP]
        settings = crud.list_settings(db, storyline_id)[:_ROSTER_CAP]
    except APIError:
        return "", {}, {}

    char_lookup: dict[str, str] = {}
    char_lines: list[str] = []
    for i, c in enumerate(characters, start=1):
        char_lookup.setdefault(_norm(c.name), c.id)
        detail = " · ".join(p for p in (c.role, c.traits) if (p or "").strip())
        char_lines.append(f"{i}. {c.name}" + (f" — {detail}" if detail else ""))

    setting_lookup: dict[str, str] = {}
    setting_lines: list[str] = []
    for i, s in enumerate(settings, start=1):
        setting_lookup.setdefault(_norm(s.name), s.id)
        detail = " · ".join(p for p in (s.type, s.desc) if (p or "").strip())
        setting_lines.append(f"{i}. {s.name}" + (f" — {detail}" if detail else ""))

    chars_text = "\n".join(char_lines) if char_lines else "(none)"
    settings_text = "\n".join(setting_lines) if setting_lines else "(none)"
    block = (
        "\n\nRoster — choose the cast and setting only from these.\n"
        f"Characters:\n{chars_text}\n\nSettings:\n{settings_text}"
    )
    return block, char_lookup, setting_lookup


def _norm(name: str) -> str:
    """Case/whitespace-folded key for tolerant name → id matching."""
    return " ".join((name or "").split()).casefold()


def draft_scenario(
    db: Session,
    seed: str,
    docs_overview: str | None = None,
    storyline_id: str | None = None,
    *,
    reasoning: ReasoningEffort = DEFAULT_AUTHORING_EFFORT,
) -> ScenarioDraftResponse:
    """Draft a scenario (fields + a roster-grounded cast & setting) from a seed."""
    seed = (seed or "").strip()
    if not seed:
        raise APIError(400, "bad_request", "Describe the scene in a sentence to draft it.")
    base_url, api_key, model, params = resolve_llm(db)

    roster_block, char_lookup, setting_lookup = _roster_block(db, storyline_id)
    user = (
        f"Scene seed: {seed}"
        f"{world_context(db, storyline_id)}"
        f"{roster_block}"
        f"{docs_block(docs_overview)}"
    )
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

    # Resolve cast names → ids, dropping unknowns and de-duplicating (order kept).
    cast_ids: list[str] = []
    raw_cast = data.get("cast")
    if isinstance(raw_cast, list):
        for entry in raw_cast:
            cid = char_lookup.get(_norm(str(entry)))
            if cid and cid not in cast_ids:
                cast_ids.append(cid)

    # Resolve the single setting name → id, or "" when it doesn't match.
    setting_id = setting_lookup.get(_norm(_s("setting")), "")

    return ScenarioDraftResponse(
        title=_s("title"),
        genre=_s("genre"),
        tone=_s("tone"),
        goal=_s("goal"),
        opening=_s("opening"),
        cast_ids=cast_ids,
        setting_id=setting_id,
    )


def generate_scene_art_prompts(
    db: Session,
    *,
    title: str = "",
    genre: str | None = None,
    tone: str | None = None,
    goal: str | None = None,
    opening: str | None = None,
    setting_name: str | None = None,
    setting_desc: str | None = None,
    notes: str | None = None,
    reasoning: ReasoningEffort = DEFAULT_AUTHORING_EFFORT,
) -> SceneArtPromptResponse:
    """Write the watercolor positive/negative ComfyUI prompts for a scenario moment."""
    fields = {
        "Scene title": title,
        "Genre": genre,
        "Tone": tone,
        "Goal": goal,
        "Opening prose": opening,
        "Setting": setting_name,
        "Setting description": setting_desc,
        "Notes": notes,
    }
    described = "\n".join(
        f"{k}: {v}".strip() for k, v in fields.items() if (v or "").strip()
    )
    if not described:
        raise APIError(
            400,
            "bad_request",
            "Describe the scenario (at least a title or tone) to generate scene-art prompts.",
        )
    base_url, api_key, model, params = resolve_llm(db)
    messages = [
        {"role": "system", "content": _SCENE_ART_SYSTEM},
        {"role": "user", "content": f"Scenario:\n{described}"},
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
