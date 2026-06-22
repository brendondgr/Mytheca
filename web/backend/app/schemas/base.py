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

# Branch tags come from the frontend `EventTag` set (note: `check_request` is
# here, `character_dialogue` is not — this is deliberately NOT the EventType set).
BranchTag = Literal[
    "check_request",
    "branch_choices",
    "state_update",
    "narration",
    "character_action",
]

# The five live story-event types carried on the NDJSON stream (see app/events).
EventType = Literal[
    "narration",
    "character_dialogue",
    "character_action",
    "state_update",
    "branch_choices",
]


class CamelModel(BaseModel):
    """Base model: camelCase aliases, accepts snake_case, reads ORM attributes."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
