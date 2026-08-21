"""Shared schema base + enums.

``CamelModel`` makes every request/response serialize in camelCase so the wire
shapes match the existing frontend types in ``web/frontend/lib/types.ts`` exactly
(``castIds``, ``settingId``, ``displayName``, ``appliesTo``). ``populate_by_name``
also accepts snake_case input; ``from_attributes`` lets schemas read ORM objects.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# Visibility controls what the player sees vs. what only affects agent reasoning.
Visibility = Literal["public", "private_to_user", "private_to_character", "hidden"]

# Runtime presence of a character within a scene (Scene Presence & Director Actions).
# ``present`` is the only SELECTABLE status (the planner may pick them to speak); every
# other status keeps the character in the cast but out of the speaking pool. ``dead`` is
# terminal, ``departed``/``unconscious`` keep the body in the scene, ``left`` removes it —
# all but ``dead`` are reversible. Presence is derived from the session's
# ``character_status_change`` event log (default ``present``), never a column.
PresenceStatus = Literal["present", "unconscious", "departed", "left", "dead"]

# Branch tags come from the frontend `EventTag` set (note: `check_request` is
# here, `character_dialogue` is not — this is deliberately NOT the EventType set).
BranchTag = Literal[
    "check_request",
    "branch_choices",
    "state_update",
    "narration",
    "character_action",
]

# The live story-event types carried on the NDJSON stream (see app/events).
# ``internal_thought`` defaults to ``visibility: hidden``, but the turn engine emits it
# ``private_to_user`` so it streams to the player as a distinct "thinking" bubble while
# staying out of other characters' context (it is never pushed to ``turn_beats``).
EventType = Literal[
    "narration",
    # One first-person passage per beat — interiority, action and speech woven together
    # with the spoken words in double quotes inline. This is the form a character beat
    # takes now; ``character_dialogue`` / ``character_action`` / ``internal_thought``
    # remain on the union so sessions recorded in the older three-fragment shape replay.
    "character_prose",
    "character_dialogue",
    "character_action",
    "internal_thought",
    "state_update",
    "branch_choices",
    "character_status_change",
    "scene_image",
]


class CamelModel(BaseModel):
    """Base model: camelCase aliases, accepts snake_case, reads ORM attributes."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
