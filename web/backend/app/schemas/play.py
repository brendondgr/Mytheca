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
    narrative-direction tag of a branch/path the player selected (legacy; the engine
    opened with a fuller "progression" narration). ``guidance`` (Scene Dialogue Updates)
    is the open-ended steer sent when the player selects a follow-up suggestion: it nudges
    the scene toward that general direction while the AI still produces original, unscripted
    dialogue — it does NOT dictate a beat-by-beat script the way ``outcome`` did.
    """

    session_id: str | None = None
    text: str
    directed_at: str | None = None
    mode: TurnMode = "pov"
    trace: bool = False
    outcome: str | None = None
    guidance: str | None = None
