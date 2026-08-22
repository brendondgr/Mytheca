"""NDJSON story-event envelope types.

The story-event types from ``docs/api-contract.md``, modeled as a discriminated
union on the top-level ``type`` so the backend can validate a streamed event with
one call (``story_event_adapter.validate_python(obj)``). Wire shape is camelCase
(``scenarioId``, ``sessionId``, ``characterId``). ``internal_thought`` is a
conditioning-only event (``visibility: hidden``) persisted but withheld from the
client stream. Delta-streaming wrapper frames (``message_start`` / ``message_delta``
/ ``message_end``) live in ``app/events/stream.py`` — they are transport frames,
not persisted story events, so they are intentionally not part of this union.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field, TypeAdapter

from app.schemas.base import CamelModel, EventType, PresenceStatus, Visibility

# ---- payloads (the `data` of each event) -----------------------------------


class StatPatch(CamelModel):
    """A stat change carried on a state_update (see api-contract §Stat changes)."""

    character_id: str
    key: str
    delta: int | None = None
    value: int | None = None
    reason: str = ""


class BeatTake(CamelModel):
    """One version of a beat's prose.

    A re-roll keeps the old take rather than replacing it: the player asked for a *different*
    line, not for the previous one to stop existing, and often the first was better. Takes
    live **inside the beat's own row** (``data.takes``) rather than as extra events — a second
    row would need a ``seq``, which would either break ``UNIQUE (session_id, seq)`` or poison
    the transcript's ordering. One beat keeps one position in the scene however many times it
    is re-rolled.
    """

    id: str
    text: str
    ts: str = ""


class ImageTake(CamelModel):
    """One rendered version of a scene image, kept for the same reason as :class:`BeatTake`."""

    id: str
    url: str
    prompt: str = ""
    negative: str = ""
    caption: str = ""
    ts: str = ""


class TakesMixin(CamelModel):
    """Alternate versions of a prose beat, and which one is showing.

    Both default to empty/zero, so every row written before this, every delta frame and every
    existing test is unchanged. ``text`` always mirrors the active take — it stays the single
    source of truth for the buffer, the export, reload and the moment prompts, none of which
    need to know takes exist.
    """

    takes: list[BeatTake] = Field(default_factory=list)
    active_take: int = 0


class NarrationData(TakesMixin):
    text: str
    done: bool = True


class CharacterProseData(TakesMixin):
    """One character beat as a single first-person passage.

    The whole beat — what they notice, what they do, what they say — in their own voice,
    with spoken words in double quotes inline. Replaces the old thought/action/dialogue
    triple, which asked the reader to reassemble a paragraph the model already had.
    """

    character_id: str
    text: str
    done: bool = True


class CharacterDialogueData(TakesMixin):
    character_id: str
    text: str
    done: bool = True


class CharacterActionData(CamelModel):
    character_id: str
    text: str


class InternalThoughtData(CamelModel):
    """A character's private in-voice thinking.

    Streamed to the PLAYER (``visibility: private_to_user``) as the muted line above the
    speaker's dialogue, and kept out of every other character's context. It delta-streams
    like visible prose — the thought is written before the spoken line, so it is the
    first thing a turn can actually show.
    """

    character_id: str
    text: str
    done: bool = True


class StateUpdateData(CamelModel):
    # Partial scenario-state patch; stat changes ride in `stat`.
    patch: dict = Field(default_factory=dict)
    stat: StatPatch | None = None


class BranchChoiceOption(CamelModel):
    # No dice/checks (D11): a branch is a narrative fork resolved by the player's
    # selection + the characters' in-character response. ``outcome`` is a direction
    # tag (de-escalate / escalate / bribe …), never a stat test.
    label: str
    outcome: str = ""


class BranchChoicesData(CamelModel):
    """Follow-up options for the player — and, optionally, a question above them.

    ``prompt`` is set only when the **planner** stopped the turn to ask where the story
    should go (its ``ask`` action): the player's line left the direction genuinely open,
    and guessing would commit the scene to something they did not choose. Empty for the
    ordinary end-of-turn suggestions, which are offered, not asked.
    """

    prompt: str = ""
    choices: list[BranchChoiceOption] = Field(default_factory=list)


class CastRequestData(CamelModel):
    """The scene is *asking* for a character who is not in it. **Never an arrival.**

    The owner's rule for this feature is that the AI must never introduce a character on its
    own initiative — "I feel like the AI will abuse it and bring in a character for the fun
    of it when we don't need it". So there is deliberately **no planner action** that brings
    someone in. A request is raised only when the player themselves named an absent character
    (a pinned directive whose actor is away, or a plain name match against the direction
    text), and it changes nothing on its own: presence moves only when the player accepts,
    through the same manual ``character_status_change`` path the cast rail already uses.

    Building it as an event rather than as a planner action is what keeps that rule literally
    true — the scene can raise a question, and only the player can answer it.
    """

    character_id: str
    #: Why the scene is asking — the requirement or phrase that named them, shown verbatim
    #: so the player can see what they wrote rather than a generic prompt.
    reason: str = ""


class CharacterStatusChangeData(CamelModel):
    """A character's scene-presence transition (Scene Presence & Director Actions).

    Carries the new ``status`` (see :data:`~app.schemas.base.PresenceStatus`), a free-text
    ``reason`` for the audit trail/UI, and ``auto`` — ``True`` when the engine detected it
    (a stat trigger, the planner's ``exit`` action, or a self-declaration), ``False`` for a
    manual player override. The client shows an undoable toast for ``auto`` transitions.
    """

    character_id: str
    status: PresenceStatus
    reason: str = ""
    auto: bool = True


class SceneImageData(CamelModel):
    """A rendered picture of the moment the scene is in (player-triggered).

    Written by ``agents.moment_agent`` and rendered by ``services.scene_moment``:
    ``url`` is the relative ``/media/moments/<uuid>.webp`` path of the landscape
    WebP, ``prompt``/``negative`` are the ComfyUI prompts that produced it (kept so
    the picture is reproducible and reviewable), ``caption`` is a one-line
    description used as the image's alt text and its enlarged-view label, and
    ``characterIds`` names who is depicted (never by name inside the prompt — the
    prompt describes appearance and action).
    """

    url: str
    prompt: str = ""
    negative: str = ""
    caption: str = ""
    character_ids: list[str] = Field(default_factory=list)
    #: The art style the picture was painted in (``app.content.art_styles``). Recorded so a
    #: repaint can start from the look the beat already has rather than the global default.
    #: Empty on rows written before styles existed.
    style: str = ""
    #: Alternate renders, kept when the player asks for another. ``url``/``prompt``/
    #: ``caption`` above always mirror the active one.
    takes: list[ImageTake] = Field(default_factory=list)
    active_take: int = 0


# ---- envelope (shared base + one class per type) ---------------------------


class EventEnvelope(CamelModel):
    """Fields shared by every story event."""

    id: str
    seq: int = 0
    scenario_id: str
    session_id: str
    ts: str  # ISO-8601
    visibility: Visibility = "public"


class NarrationEvent(EventEnvelope):
    type: Literal["narration"] = "narration"
    data: NarrationData


class CharacterProseEvent(EventEnvelope):
    type: Literal["character_prose"] = "character_prose"
    data: CharacterProseData


class CharacterDialogueEvent(EventEnvelope):
    type: Literal["character_dialogue"] = "character_dialogue"
    data: CharacterDialogueData


class CharacterActionEvent(EventEnvelope):
    type: Literal["character_action"] = "character_action"
    data: CharacterActionData


class InternalThoughtEvent(EventEnvelope):
    type: Literal["internal_thought"] = "internal_thought"
    visibility: Visibility = "hidden"
    data: InternalThoughtData


class StateUpdateEvent(EventEnvelope):
    type: Literal["state_update"] = "state_update"
    data: StateUpdateData


class BranchChoicesEvent(EventEnvelope):
    type: Literal["branch_choices"] = "branch_choices"
    data: BranchChoicesData


class CharacterStatusChangeEvent(EventEnvelope):
    type: Literal["character_status_change"] = "character_status_change"
    data: CharacterStatusChangeData


class CastRequestEvent(EventEnvelope):
    type: Literal["cast_request"] = "cast_request"
    data: CastRequestData


class SceneImageEvent(EventEnvelope):
    type: Literal["scene_image"] = "scene_image"
    data: SceneImageData


StoryEvent = Annotated[
    Union[
        NarrationEvent,
        CharacterProseEvent,
        CharacterDialogueEvent,
        CharacterActionEvent,
        InternalThoughtEvent,
        StateUpdateEvent,
        BranchChoicesEvent,
        CharacterStatusChangeEvent,
        CastRequestEvent,
        SceneImageEvent,
    ],
    Field(discriminator="type"),
]

# Validate/parse any incoming event dict into the right typed model.
story_event_adapter: TypeAdapter[StoryEvent] = TypeAdapter(StoryEvent)

__all__ = [
    "EventType",
    "StatPatch",
    "NarrationData",
    "CharacterDialogueData",
    "CharacterActionData",
    "InternalThoughtData",
    "StateUpdateData",
    "BranchChoiceOption",
    "BranchChoicesData",
    "CharacterStatusChangeData",
    "CastRequestData",
    "SceneImageData",
    "EventEnvelope",
    "NarrationEvent",
    "CharacterDialogueEvent",
    "CharacterActionEvent",
    "InternalThoughtEvent",
    "StateUpdateEvent",
    "BranchChoicesEvent",
    "CharacterStatusChangeEvent",
    "CastRequestEvent",
    "SceneImageEvent",
    "StoryEvent",
    "story_event_adapter",
]
