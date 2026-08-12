"""In-narrative image generation — the live scene → a persisted ``scene_image`` beat.

The player's **Create image** action, end to end. Stage one asks
``agents.moment_agent`` to describe what is happening; stage two renders that
prompt through the same ComfyUI client the portrait and scene-art pipelines use,
at a **landscape 1216×832** frame (a moment is a scene, not a head-and-shoulders
portrait — and unlike those pipelines the frame is pinned here rather than taken
from the Options defaults, which are tuned for portraits). The WebP is written
under ``MEDIA_DIR/moments`` and the picture is persisted as a ``scene_image`` story
event on the session, so it keeps its place in the transcript on reload and in the
export.

The work is exposed as a generator of progress stages so the route can stream it:
a render takes tens of seconds, and the player should see which half they are
waiting on.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.agents import moment_agent
from app.agents._common import resolve_llm
from app.agents.moment_agent import FramedCharacter
from app.core.config import get_settings
from app.core.errors import APIError
from app.events.envelope import SceneImageEvent, StoryEvent
from app.events.stream import build_event
from app.models import Character, Event, Scenario, Setting
from app.schemas.play import MomentPromptResponse, MomentRequest, MomentStageFrame
from app.services import comfyui, crud, events_store, presence, settings_store
from app.services.media import save_webp

# The moment frame — landscape, ~1 MP, both sides divisible by 64. Pinned here (not
# read from the Options defaults) so a picture of the scene is always wider than tall.
_MOMENT_W = 1216
_MOMENT_H = 832
_SEED_MAX = 2**32 - 1

# How many recent beats the prompt writer looks back over by default, and the hard
# bounds on a caller-supplied window. A moment is the *last* thing that happened;
# too deep a window blurs it into the whole scene.
_DEFAULT_BEATS = 8
_MIN_BEATS = 2
_MAX_BEATS = 40

# Event types that carry visible prose worth showing the prompt writer.
_BEAT_TYPES = ("narration", "character_dialogue", "character_action", "user_turn")


def _moments_dir() -> Path:
    """Directory moment images are written to (patched in tests)."""
    return get_settings().moments_dir


def _render_beat(event: Event, names: dict[str, str]) -> str:
    """One persisted event as a transcript line the prompt writer can read."""
    text = str((event.data or {}).get("text") or "").strip()
    if not text:
        return ""
    who = names.get(str((event.data or {}).get("characterId") or ""), "")
    if event.type == "narration":
        return f"Narrator: {text}"
    if event.type == "user_turn":
        pov = names.get(str((event.data or {}).get("pov") or ""), "")
        return f"{pov or 'The player'}: {text}"
    if event.type == "character_action":
        return f"{who or 'Someone'} (action): {text}"
    return f"{who or 'Someone'}: {text}"


def _recent_beats(events: list[Event], names: dict[str, str], limit: int) -> list[Event]:
    """The last ``limit`` visible beats of the session, oldest first."""
    visible = [e for e in events if e.type in _BEAT_TYPES and _render_beat(e, names)]
    return visible[-limit:]


def _in_frame(
    beats: list[Event],
    cast: list[Character],
    presence_map: dict[str, str],
) -> list[Character]:
    """Who the picture should show: present cast members active in the recent beats.

    A cast member who has been silent for the whole window is not painted in — the
    image is of *this* moment, not of the scenario's roster. Order follows the
    scene (earliest speaker first) so the prompt reads left-to-right consistently.
    Falls back to the present cast when the window names nobody (e.g. pure narration).
    """
    by_id = {c.id: c for c in cast}
    ordered: list[Character] = []
    for event in beats:
        data = event.data or {}
        cid = str(data.get("characterId") or data.get("pov") or "")
        char = by_id.get(cid)
        if char and char not in ordered and presence.status_for(presence_map, cid) == "present":
            ordered.append(char)
    if ordered:
        return ordered
    return [c for c in cast if presence.status_for(presence_map, c.id) == "present"]


def _last_action(character_id: str, beats: list[Event], names: dict[str, str]) -> str:
    """The most recent thing this character said or did, for the "doing now" hint."""
    for event in reversed(beats):
        if str((event.data or {}).get("characterId") or "") != character_id:
            continue
        text = str((event.data or {}).get("text") or "").strip()
        if not text:
            continue
        if event.type == "character_action":
            return text
        return f'says "{text[:160]}"'
    return ""


def _framed(chars: list[Character], beats: list[Event], names: dict[str, str]):
    return [
        FramedCharacter(
            id=c.id,
            name=c.name,
            role=c.role or "",
            appearance=c.appearance or "",
            portrait_positive=c.portrait_positive or "",
            doing=_last_action(c.id, beats, names),
        )
        for c in chars
    ]


def _place_block(setting: Setting | None) -> str:
    if setting is None:
        return ""
    fields = {
        "Name": setting.name,
        "Type": setting.type,
        "Description": setting.desc,
        "Atmosphere": setting.atmosphere,
        "Current state": setting.current_state,
    }
    return "\n".join(f"{k}: {v}" for k, v in fields.items() if (v or "").strip())


def _world_block(scenario: Scenario) -> str:
    storyline = scenario.storyline
    bits = []
    if storyline is not None:
        bits.append(f"World: {storyline.title} ({storyline.genre}).")
    bits.append(f"Scene: {scenario.title} — genre {scenario.genre}, tone {scenario.tone}.")
    return "\n".join(bits)


def _setting_of(db: Session, scenario: Scenario) -> Setting | None:
    """The scene's place — a *soft* reference, so a stale id is simply no place."""
    if not scenario.setting_id:
        return None
    try:
        return crud.get_setting(db, scenario.setting_id)
    except APIError:
        return None


@dataclass
class MomentContext:
    """Everything the render needs, resolved *before* the 200 stream opens.

    Mirrors ``turn_engine.validate_turn_inputs``: an unknown scenario, a session that
    is not this scenario's, an empty scene, or an unconfigured ComfyUI/LLM must be a
    normal error envelope, not a terminal error frame the player waits for.
    """

    scenario: Scenario
    session_id: str
    comfy_base: str
    conn: tuple
    beats: list[str]
    cast: list[FramedCharacter]
    world: str
    place: str


def prepare_moment(db: Session, scenario_id: str, data: MomentRequest) -> MomentContext:
    """Validate and gather the scene for a moment render. Raises :class:`APIError`."""
    scenario = crud.get_scenario(db, scenario_id)  # 404 when unknown
    session = events_store.get_session(db, scenario_id, data.session_id)  # 404/400

    comfy_base = settings_store.resolve_comfy_base_url(db, None)
    if not comfy_base:
        raise APIError(400, "bad_request", "Configure a ComfyUI base URL in Options first.")
    # Resolve the LLM here too, so an unconfigured model is a clean 400 up front
    # rather than a mid-stream failure after the player has waited on it.
    conn = resolve_llm(db)

    cast = [
        c
        for c in crud.list_characters(db, scenario.storyline_id)
        if c.id in (scenario.cast_ids or [])
    ]
    names = {c.id: c.name for c in cast}
    window = max(_MIN_BEATS, min(int(data.beats or _DEFAULT_BEATS), _MAX_BEATS))
    recent = _recent_beats(events_store.session_events(db, session.id), names, window)
    if not recent:
        raise APIError(400, "bad_request", "Play at least one beat before capturing the moment.")

    presence_map = presence.current_presence(db, session.id)
    return MomentContext(
        scenario=scenario,
        session_id=session.id,
        comfy_base=comfy_base,
        conn=conn,
        beats=[_render_beat(e, names) for e in recent],
        cast=_framed(_in_frame(recent, cast, presence_map), recent, names),
        world=_world_block(scenario),
        place=_place_block(_setting_of(db, scenario)),
    )


def generate_moment(
    db: Session,
    ctx: MomentContext,
    *,
    width: int | None = None,
    height: int | None = None,
) -> Iterator[MomentStageFrame | StoryEvent]:
    """Write the prompt, render it, persist the beat — yielding a frame per stage.

    Yields a ``MomentStageFrame`` as each stage opens and finally the persisted
    ``scene_image`` event. A failure raises :class:`APIError`, which the route turns
    into the terminal in-band error frame.
    """
    yield MomentStageFrame(stage="prompt", message="Reading the scene…")

    prompts: MomentPromptResponse = moment_agent.write_moment_prompt(
        db,
        beats=ctx.beats,
        cast=ctx.cast,
        world=ctx.world,
        place=ctx.place,
        conn=ctx.conn,
    )

    yield MomentStageFrame(
        stage="render",
        message="Painting the moment…",
        positive=prompts.positive,
        caption=prompts.caption,
    )

    comfy = settings_store.get_comfy(db)
    params = comfy.params
    image_bytes, _info = comfyui.generate(
        ctx.comfy_base,
        comfy.workflow,
        positive=prompts.positive,
        negative=prompts.negative or params.negative_prompt or None,
        steps=params.steps,
        cfg=params.cfg,
        width=width or _MOMENT_W,
        height=height or _MOMENT_H,
        seed=random.randint(0, _SEED_MAX),
        batch_size=1,
    )
    filename = save_webp(_moments_dir(), image_bytes)

    event = build_event(
        "scene_image",
        {
            "url": f"/media/moments/{filename}",
            "prompt": prompts.positive,
            "negative": prompts.negative,
            "caption": prompts.caption,
            "characterIds": [c.id for c in ctx.cast],
        },
        scenario_id=ctx.scenario.id,
        session_id=ctx.session_id,
        seq=events_store.next_seq(db, ctx.session_id),
    )
    events_store.persist_story_event(db, event)
    events_store.touch_session(db, ctx.session_id)
    assert isinstance(event, SceneImageEvent)  # build_event validates the union
    yield event
