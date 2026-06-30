"""Stream helpers: envelope construction + NDJSON serialization.

The turn engine builds typed story events through :func:`build_event` (so every
emitted event is validated against the discriminated union by construction) and
serializes them to NDJSON lines via :func:`to_ndjson_line` — the same
``model_dump_json(by_alias=True) + "\\n"`` shape the build/triage streams use.

Delta-streaming wrapper frames (``message_start`` / ``message_delta`` /
``message_end``) are added in a later phase; for now visible messages stream as
full events.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.core.ids import new_id
from app.events.envelope import StoryEvent, story_event_adapter
from app.schemas.base import CamelModel, EventType, Visibility


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string (the envelope ``ts``)."""
    return datetime.now(UTC).isoformat()


def build_event(
    type_: EventType,
    data: dict[str, Any],
    *,
    scenario_id: str,
    session_id: str,
    seq: int,
    visibility: Visibility | None = None,
    event_id: str | None = None,
    ts: str | None = None,
) -> StoryEvent:
    """Construct and validate a single story event.

    Returns the concrete typed model (e.g. ``CharacterDialogueEvent``) via the
    discriminated-union adapter, so an invalid ``type``/``data`` shape raises here
    rather than slipping onto the wire. ``visibility`` defaults to the type's own
    default (``hidden`` for ``internal_thought``, else ``public``) when omitted.
    """
    payload: dict[str, Any] = {
        "type": type_,
        "id": event_id or new_id("ev"),
        "seq": seq,
        "scenario_id": scenario_id,
        "session_id": session_id,
        "ts": ts or now_iso(),
        "data": data,
    }
    if visibility is not None:
        payload["visibility"] = visibility
    return story_event_adapter.validate_python(payload)


def to_ndjson_line(frame: BaseModel) -> str:
    """Serialize a story event (or transport frame) to one NDJSON line."""
    return frame.model_dump_json(by_alias=True) + "\n"


class TurnErrorFrame(CamelModel):
    """Terminal in-band error frame for the turn stream.

    Mirrors ``BuildErrorEvent`` / ``TriageErrorEvent``: pre-flight failures return a
    normal ``400`` before the ``200`` stream opens, but a mid-stream failure can only
    be reported in-band, so the route yields this as the final line.
    """

    type: Literal["error"] = "error"
    message: str
