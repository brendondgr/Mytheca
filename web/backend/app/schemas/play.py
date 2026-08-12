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

from app.schemas.base import CamelModel, PresenceStatus, Visibility

# One engine, two render styles (D1): POV (interstitials off) or Narrator (on).
TurnMode = Literal["pov", "narrator"]


class PresenceRequest(CamelModel):
    """A manual player override of a character's scene presence (Scene Presence & Director
    Actions).

    Sets ``characterId`` to any :data:`~app.schemas.base.PresenceStatus` on the given
    session — including a resurrection back to ``present`` (the player has final say; the
    endpoint is intentionally not bound by the engine's ``can_transition`` guard). Persists a
    ``character_status_change`` event with ``auto=False`` so the client does NOT show an
    undo toast (a manual change is already the player's intent)."""

    session_id: str
    character_id: str
    status: PresenceStatus
    reason: str = ""


class TurnRequest(CamelModel):
    """One player turn.

    ``sessionId`` resumes an existing play session; omit it to start a new one.
    ``directedAt`` is the optional character id the player is addressing. ``mode``
    selects POV (default) or Narrator rendering — the *same* loop, narrator
    interstitials on or off. ``trace`` opts into diagnostic ``trace`` frames
    interleaved on the stream (the story player's Inspector panel) — off by default so
    the default stream + the story-event contract are unchanged. ``outcome`` is the
    narrative-direction tag of a branch/path the player selected (legacy; the engine
    opened with a fuller "progression" narration).

    ``povCharacterId`` is the *Player POV* control: when set to a present cast member's
    id, the player's line **is that character's line** — it is seeded into the turn as a
    ``character`` beat (so later speakers react to *Mei said X*), persisted on the
    ``user_turn`` row, and the POV character is removed from the AI's selectable roster so
    it is never voiced by the model. ``None`` (the default) is today's guide/narrator
    behavior. NOTE: this is orthogonal to ``mode`` — ``mode`` is a *rendering* switch
    (narrator interstitials on/off); ``povCharacterId`` is *who the player speaks as*.

    A selected follow-up suggestion no longer submits a turn on its own: the story player
    writes the suggested text into the composer for the player to review/edit and send as
    an ordinary ``text`` turn (request #2), so there is no separate open-ended steer field.
    """

    session_id: str | None = None
    text: str
    directed_at: str | None = None
    mode: TurnMode = "pov"
    trace: bool = False
    outcome: str | None = None
    pov_character_id: str | None = None


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


# ---- in-narrative image generation (the player's "Create image" action) -----


class MomentPromptResponse(CamelModel):
    """The prompts ``agents.moment_agent`` wrote for a picture of the current moment.

    ``positive`` describes the moment in ComfyUI phrase form — every figure by
    appearance and action, never by name (enforced by ``moment_agent.strip_names``).
    ``caption`` is plain English for a reader who cannot see the image, and MAY use
    names; it becomes the event's alt text.
    """

    positive: str
    negative: str = ""
    caption: str = ""


class MomentRequest(CamelModel):
    """Ask for a picture of where the scene stands right now.

    ``sessionId`` is required — a moment belongs to a play-through, and the beats it
    depicts are read from that session's event log. ``beats`` optionally narrows how
    far back the shot looks (defaults to the scenario's own ``contextBeats`` window,
    clamped); everything else (who is in frame, the place, the world) is derived
    server-side, so the client cannot desync from the story.
    """

    session_id: str
    beats: int | None = None


class MomentStageFrame(CamelModel):
    """Progress on the moment stream: which of the two stages is running.

    ``prompt`` while the agent writes, ``render`` while ComfyUI paints (re-emitted as
    the keep-alive heartbeat so a silent socket never looks dead). ``positive`` is
    filled once the prompt exists, so the UI can show what is being painted.
    """

    type: Literal["moment_stage"] = "moment_stage"
    stage: Literal["prompt", "render"]
    message: str = ""
    positive: str = ""
    caption: str = ""
