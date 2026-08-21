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


class NarrationData(CamelModel):
    text: str
    done: bool = True


class CharacterProseData(CamelModel):
    """One character beat as a single first-person passage.

    The whole beat — what they notice, what they do, what they say — in their own voice,
    with spoken words in double quotes inline. Replaces the old thought/action/dialogue
    triple, which asked the reader to reassemble a paragraph the model already had.
    """

    character_id: str
    text: str
    done: bool = True


class CharacterDialogueData(CamelModel):
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
    "SceneImageData",
    "EventEnvelope",
    "NarrationEvent",
    "CharacterDialogueEvent",
    "CharacterActionEvent",
    "InternalThoughtEvent",
    "StateUpdateEvent",
    "BranchChoicesEvent",
    "CharacterStatusChangeEvent",
    "SceneImageEvent",
    "StoryEvent",
    "story_event_adapter",
]
