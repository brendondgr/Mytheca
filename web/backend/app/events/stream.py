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

from pydantic import BaseModel, Field

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


# Visible prose (narration, character_dialogue) is delta-streamed by emitting the
# **same event** (same id + seq) repeatedly with incremental ``text`` and ``done:
# false`` until the final chunk sets ``done: true`` — the client accumulates by id.
# This reuses the ``done`` field already on those payloads; the persisted row holds
# the full text. (``character_action`` has no ``done`` field and streams as one event.)
_DELTA_CHUNK_CHARS = 48


def chunk_text(text: str, max_chunk_chars: int = _DELTA_CHUNK_CHARS) -> list[str]:
    """Split text into incremental delta chunks; ``"".join(chunks) == text`` exactly.

    Chunks break only on word boundaries (the breaking space stays at the end of the
    chunk), so concatenating them on the client reconstructs the text verbatim.
    Always returns at least one chunk (``[""]`` for empty text).
    """
    if not text:
        return [""]
    chunks: list[str] = []
    start, n = 0, len(text)
    while start < n:
        end = min(start + max_chunk_chars, n)
        if end < n:
            space = text.find(" ", end)
            end = space + 1 if space != -1 else n  # keep the space with this chunk
        chunks.append(text[start:end])
        start = end
    return chunks


class TurnErrorFrame(CamelModel):
    """Terminal in-band error frame for the turn stream.

    Mirrors ``BuildErrorEvent`` / ``TriageErrorEvent``: pre-flight failures return a
    normal ``400`` before the ``200`` stream opens, but a mid-stream failure can only
    be reported in-band, so the route yields this as the final line.
    """

    type: Literal["error"] = "error"
    message: str


class TurnTraceFrame(CamelModel):
    """Diagnostic trace frame for the turn stream (opt-in via ``TurnRequest.trace``).

    **Not** a persisted story event — a transport frame (like :class:`TurnErrorFrame`)
    the engine interleaves to explain, in order, what the turn loop did and *why*: the
    Director's speaker choice + rationale, each character's hidden thinking, stat clamps,
    the mid-turn re-rank / cascade, the reflection interlude. The story player's
    **Inspector** panel renders these in order; the transcript ignores them. Emitted only
    when the caller sets ``trace: true``, so the default stream and the story-event
    contract are unchanged. ``n`` orders the frames within one turn; ``step`` is a stable
    machine key (``turn`` opens each turn); ``title``/``detail`` are human-readable and
    ``data`` carries the structured payload (speakers, deltas, order changes, …)."""

    type: Literal["trace"] = "trace"
    n: int = 0
    step: str
    title: str
    detail: str = ""
    data: dict = Field(default_factory=dict)
