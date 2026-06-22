"""Story-event envelope types (chat scaffold). See docs/api-contract.md."""

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
    NarrationData,
    NarrationEvent,
    StateUpdateData,
    StateUpdateEvent,
    StatPatch,
    StoryEvent,
    story_event_adapter,
)

__all__ = [
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
