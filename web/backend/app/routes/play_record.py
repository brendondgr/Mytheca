"""Play-record routes — mutate a scenario's play-throughs and their history.

Everything in this module changes the **record** rather than advancing it: create,
rename and delete a play-through here; later phases of
``docs/plans/control-over-the-record.md`` add branch, rewind, edit and re-roll alongside
them. It is a separate module from ``routes/play.py`` deliberately — that file already
carries the turn stream, the moment stream, presence, relationships, history and export,
and folding the record surface into it would push it past the repo's file-length rule.

Both modules mount under the same ``/play`` prefix and render the identical
:class:`~app.schemas.play.SessionSummary` via ``events_store.session_summary``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.play import (
    SessionCreateRequest,
    SessionRenameRequest,
    SessionSummary,
)
from app.services import crud, events_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/play", tags=["play"])


@router.post("/{scenario_id}/sessions", response_model=SessionSummary, status_code=201)
def create_play_session(
    scenario_id: str,
    data: SessionCreateRequest | None = None,
    db: Session = Depends(get_db),
) -> SessionSummary:
    """Start a **fresh** play-through of a scenario.

    The point of this endpoint is what it does *not* do: it never touches the scenario's
    existing sessions. Before it existed the only way to get a new play-through was to
    send a turn with no ``sessionId``, and the story player never did that — it resumed
    the most recent session unconditionally, so a scenario could only ever hold one story.
    """
    scenario = crud.get_scenario(db, scenario_id)
    session = events_store.create_session(
        db, scenario.id, name=(data.name if data else None)
    )
    return events_store.session_summary(db, session)


@router.patch("/{scenario_id}/sessions/{session_id}", response_model=SessionSummary)
def rename_play_session(
    scenario_id: str,
    session_id: str,
    data: SessionRenameRequest,
    db: Session = Depends(get_db),
) -> SessionSummary:
    """Relabel a play-through. A blank name clears the label and restores the
    first-player-line fallback."""
    # Validates that the session exists AND belongs to this scenario (404 / 400).
    events_store.get_session(db, scenario_id, session_id)
    session = events_store.rename_session(db, session_id, data.name)
    return events_store.session_summary(db, session)


@router.delete("/{scenario_id}/sessions/{session_id}", status_code=204)
def delete_play_session(
    scenario_id: str,
    session_id: str,
    db: Session = Depends(get_db),
) -> Response:
    """Delete a play-through, its events and its diagnostic traces.

    The ``events`` and ``turn_traces`` rows go with it through their existing
    ``ondelete="CASCADE"`` FKs; the Redis buffer is cleared best-effort inside
    ``events_store.delete_session``. A play-through forked *from* this one survives —
    ``parent_session_id`` is ``ondelete="SET NULL"`` — it simply loses its recorded lineage.
    """
    events_store.get_session(db, scenario_id, session_id)
    events_store.delete_session(db, session_id)
    return Response(status_code=204)
