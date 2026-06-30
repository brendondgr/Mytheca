"""Play (turn-loop) request schemas.

``POST /api/play/{scenarioId}/turn`` submits one player turn and streams the
resulting story events back as NDJSON (the response is the stream itself — there is
no JSON response body). The terminal in-band error frame is
``app.events.stream.TurnErrorFrame``.
"""

from __future__ import annotations

from app.schemas.base import CamelModel


class TurnRequest(CamelModel):
    """One player turn.

    ``sessionId`` resumes an existing play session; omit it to start a new one.
    ``directedAt`` is the optional character id the player is addressing.
    """

    session_id: str | None = None
    text: str
    directed_at: str | None = None
