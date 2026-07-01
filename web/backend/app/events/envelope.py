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

from app.schemas.base import CamelModel, EventType, Visibility

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


class CharacterDialogueData(CamelModel):
    character_id: str
    text: str
    done: bool = True


class CharacterActionData(CamelModel):
    character_id: str
    text: str


class InternalThoughtData(CamelModel):
    """A character's hidden in-voice thinking (conditioning only, never shown).

    Emitted with ``visibility: hidden`` (Step 5 / §7 of the turn-loop plan): it is
    persisted as conditioning context but withheld from the client stream.
    """

    character_id: str
    text: str


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
    choices: list[BranchChoiceOption] = Field(default_factory=list)


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


StoryEvent = Annotated[
    Union[
        NarrationEvent,
        CharacterDialogueEvent,
        CharacterActionEvent,
        InternalThoughtEvent,
        StateUpdateEvent,
        BranchChoicesEvent,
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
    "EventEnvelope",
    "NarrationEvent",
    "CharacterDialogueEvent",
    "CharacterActionEvent",
    "InternalThoughtEvent",
    "StateUpdateEvent",
    "BranchChoicesEvent",
    "StoryEvent",
    "story_event_adapter",
]
