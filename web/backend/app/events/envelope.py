"""NDJSON story-event envelope types (chat scaffold).

The five event types from ``docs/api-contract.md``, modeled as a discriminated
union on the top-level ``type`` so the backend can validate a streamed event with
one call (``story_event_adapter.validate_python(obj)``). Wire shape is camelCase
(``scenarioId``, ``sessionId``, ``characterId``). No streaming/turn logic yet —
this is the type scaffold the future event engine will emit and validate against.
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


class StateUpdateData(CamelModel):
    # Partial scenario-state patch; stat changes ride in `stat`.
    patch: dict = Field(default_factory=dict)
    stat: StatPatch | None = None


class BranchChoiceOption(CamelModel):
    label: str
    outcome: str = ""
    check: str | None = None


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
    "StateUpdateData",
    "BranchChoiceOption",
    "BranchChoicesData",
    "EventEnvelope",
    "NarrationEvent",
    "CharacterDialogueEvent",
    "CharacterActionEvent",
    "StateUpdateEvent",
    "BranchChoicesEvent",
    "StoryEvent",
    "story_event_adapter",
]
