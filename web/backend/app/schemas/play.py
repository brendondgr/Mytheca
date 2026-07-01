"""Play (turn-loop) request schemas.

``POST /api/play/{scenarioId}/turn`` submits one player turn and streams the
resulting story events back as NDJSON (the response is the stream itself — there is
no JSON response body). The terminal in-band error frame is
``app.events.stream.TurnErrorFrame``.
"""

from __future__ import annotations

from typing import Literal

from app.schemas.base import CamelModel

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
