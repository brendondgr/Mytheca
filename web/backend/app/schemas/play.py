"""Play (turn-loop) request + session-review schemas.

``POST /api/play/{scenarioId}/turn`` submits one player turn and streams the
resulting story events back as NDJSON (the response is the stream itself — there is
no JSON response body). The terminal in-band error frame is
``app.events.stream.TurnErrorFrame``. The session-review schemas below back the
persistent-scene endpoints (``GET …/sessions``, ``GET …/sessions/{id}`` history, and
``POST …/sessions/{id}/close``) so a scenario's play-through can be reopened and
continued with its full history — turns, thoughts, and the graph/RAG trace — intact.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from app.schemas.base import CamelModel, Visibility

# One engine, two render styles (D1): POV (interstitials off) or Narrator (on).
TurnMode = Literal["pov", "narrator"]


class TurnRequest(CamelModel):
    """One player turn.

    ``sessionId`` resumes an existing play session; omit it to start a new one.
    ``directedAt`` is the optional character id the player is addressing. ``mode``
    selects POV (default) or Narrator rendering — the *same* loop, narrator
    interstitials on or off. ``trace`` opts into diagnostic ``trace`` frames
    interleaved on the stream (the story player's Inspector panel) — off by default so
    the default stream + the story-event contract are unchanged. ``outcome`` is the
    narrative-direction tag of a branch/path the player selected (the story player sends
    it when a choice is picked): the engine opens with a fuller "progression" narration
    and plays the chosen direction out over several beats rather than stopping short.
    """

    session_id: str | None = None
    text: str
    directed_at: str | None = None
    mode: TurnMode = "pov"
    trace: bool = False
    outcome: str | None = None


class SessionSummary(CamelModel):
    """One play-through's metadata for the resume list (newest ``updatedAt`` first).

    ``turnCount`` is the number of player turns taken; ``preview`` is the first
    player line (a human-readable label for the play-through).
    """

    id: str
    scenario_id: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    turn_count: int = 0
    preview: str = ""


class SessionListResponse(CamelModel):
    sessions: list[SessionSummary]


class PersistedEvent(CamelModel):
    """A stored story event in the wire-envelope shape, so the story player can replay
    it through the exact same reducers it uses for the live stream (reload = replay)."""

    type: str
    id: str
    seq: int
    scenario_id: str
    session_id: str
    ts: datetime
    visibility: Visibility
    data: dict[str, Any]


class PersistedTrace(CamelModel):
    """A stored diagnostic trace step (graph/RAG/thinking) for one turn, ordered by
    ``(turn, n)`` — folds back into the Inspector exactly like a live ``trace`` frame."""

    turn: int
    n: int
    step: str
    title: str
    detail: str
    data: dict[str, Any]


class SessionHistoryResponse(CamelModel):
    """The full record of one play-through: metadata + every event (incl. hidden
    thoughts + the ``user_turn`` rows) + every diagnostic trace step."""

    session: SessionSummary
    events: list[PersistedEvent]
    traces: list[PersistedTrace]
