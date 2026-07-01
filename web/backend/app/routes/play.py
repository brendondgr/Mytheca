"""Play route — submit a turn, stream the story events back as NDJSON.

``POST /api/play/{scenarioId}/turn`` runs the turn and returns the event stream in
its response body (``application/x-ndjson``), reusing the build/triage streaming
pattern: pre-flight failures (unknown scenario, empty text, bad session) return a
normal error envelope *before* the 200 stream opens; a mid-stream failure is the
terminal ``error`` frame.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import APIError
from app.events.stream import TurnErrorFrame, to_ndjson_line
from app.schemas.play import TurnRequest
from app.services import crud, graph_reader, turn_engine

router = APIRouter(prefix="/play", tags=["play"])

# Keep proxies (nginx) from buffering the live stream (mirrors the build/triage routes).
_STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("/{scenario_id}/turn")
def play_turn(scenario_id: str, data: TurnRequest, db: Session = Depends(get_db)):
    """Submit one player turn; stream the resulting story events (NDJSON)."""
    scenario = turn_engine.validate_turn_inputs(db, scenario_id, data)

    def _lines() -> Iterator[str]:
        try:
            for event in turn_engine.run_turn(db, scenario, data):
                yield to_ndjson_line(event)
        except APIError as exc:
            yield to_ndjson_line(TurnErrorFrame(message=exc.message))
        except Exception:  # never leak a stack trace into the stream
            yield to_ndjson_line(TurnErrorFrame(message="The turn failed unexpectedly."))

    return StreamingResponse(_lines(), media_type="application/x-ndjson", headers=_STREAM_HEADERS)


@router.get("/{scenario_id}/relationships")
def scenario_relationships(scenario_id: str, db: Session = Depends(get_db)):
    """The scenario's live character↔character relationships from the story graph.

    Best-effort: an empty list when the graph is off/unreachable (the story player then
    keeps its seed placeholder). 404 only when the scenario itself is unknown.
    """
    crud.get_scenario(db, scenario_id)  # 404 when the scenario is unknown
    return {"relationships": graph_reader.scenario_relationships(db, scenario_id)}
