"""Story-event envelope + stream-frame types. See docs/api-contract.md."""

from __future__ import annotations

from app.events.envelope import (
    BranchChoiceOption,
    BranchChoicesData,
    BranchChoicesEvent,
    CharacterActionData,
    CharacterActionEvent,
    CharacterDialogueData,
    CharacterDialogueEvent,
    EventEnvelope,
    InternalThoughtData,
    InternalThoughtEvent,
    NarrationData,
    NarrationEvent,
    StateUpdateData,
    StateUpdateEvent,
    StatPatch,
    StoryEvent,
    story_event_adapter,
)
from app.events.stream import (
    TurnErrorFrame,
    build_event,
    chunk_text,
    now_iso,
    to_ndjson_line,
)

__all__ = [
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
    # stream helpers
    "TurnErrorFrame",
    "build_event",
    "to_ndjson_line",
    "now_iso",
    "chunk_text",
]
