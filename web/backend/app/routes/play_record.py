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
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Event
from app.schemas.play import (
    BranchRequest,
    RestoredTurn,
    RewindRequest,
    RewindResponse,
    SessionCreateRequest,
    SessionRenameRequest,
    SessionSummary,
)
from app.services import crud, events_store, session_state

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


@router.post(
    "/{scenario_id}/sessions/{session_id}/branch",
    response_model=SessionSummary,
    status_code=201,
)
def branch_play_session(
    scenario_id: str,
    session_id: str,
    data: BranchRequest,
    db: Session = Depends(get_db),
) -> SessionSummary:
    """Fork a play-through at a beat into a new one, leaving the original intact.

    This is the non-destructive half of the machinery rewind uses, which is why it is built
    first: rewind's undo is implemented by calling straight into it rather than by inventing
    soft-deletion and a ``deleted_at`` column every query would then have to filter.

    The fork point is the **end of the turn** the chosen beat belongs to
    (``session_state.turn_boundary``), so the branch never inherits half a turn — the traces
    are keyed by a turn's opening seq, and presence and stats are re-derived per turn.
    """
    source = events_store.get_session(db, scenario_id, session_id)
    session_state.require_expected_seq(db, session_id, data.expected_seq)

    opening = session_state.turn_boundary(db, session_id, data.at_event_id)
    # Through the END of that turn: everything up to the next player line.
    next_turn = db.scalars(
        select(Event)
        .where(
            Event.session_id == session_id,
            Event.type == "user_turn",
            Event.seq > opening.seq,
        )
        .order_by(Event.seq)
        .limit(1)
    ).first()
    through_seq = (next_turn.seq - 1) if next_turn else session_state.latest_seq(db, session_id)

    fork = events_store.create_session(
        db,
        scenario_id,
        name=data.name,
        parent_session_id=source.id,
        fork_seq=through_seq,
    )
    session_state.copy_history(db, source.id, fork.id, through_seq=through_seq)
    return events_store.session_summary(db, fork)


@router.post("/{scenario_id}/sessions/{session_id}/rewind", response_model=RewindResponse)
def rewind_play_session(
    scenario_id: str,
    session_id: str,
    data: RewindRequest,
    db: Session = Depends(get_db),
) -> RewindResponse:
    """Cut a play-through back to a beat and hand the player's line back to them.

    The cut is at a **turn boundary** — the whole turn containing the chosen beat goes, with
    everything after it. A mid-turn cut would leave half a ``turn_traces`` record describing
    beats that no longer exist, and would strand presence and stat derivation mid-turn.

    Undo is a **branch**, not soft-deletion: with ``keepSnapshot`` the pre-cut history is
    forked into its own play-through first, so recovering it is "open that row in the tray".
    A ``deleted_at`` column would mean every query in the app grows a filter, forever, to
    support an operation the player takes rarely.

    The response carries the deleted player line back with its direction and attachments, so
    the client can put the player where they were and let them say what happens instead.
    """
    events_store.get_session(db, scenario_id, session_id)
    session_state.require_expected_seq(db, session_id, data.expected_seq)

    opening = session_state.turn_boundary(db, session_id, data.at_event_id)
    turn_data = opening.data if isinstance(opening.data, dict) else {}
    restored = RestoredTurn(
        text=str(turn_data.get("text") or ""),
        guidance=turn_data.get("guidance"),
        pov=turn_data.get("pov"),
        tagged_doc_ids=list(turn_data.get("taggedDocIds") or []),
    )

    snapshot_id: str | None = None
    if data.keep_snapshot:
        stamp = datetime.now(UTC).strftime("%H:%M")
        snapshot = events_store.create_session(
            db,
            scenario_id,
            name=f"Before rewind · {stamp}",
            parent_session_id=session_id,
            fork_seq=session_state.latest_seq(db, session_id),
        )
        session_state.copy_history(
            db, session_id, snapshot.id, through_seq=session_state.latest_seq(db, session_id)
        )
        snapshot_id = snapshot.id

    # `after_seq = opening.seq - 1` so the opening ``user_turn`` row goes too: the player is
    # about to rewrite that line, and leaving it would double it when they send.
    result = session_state.truncate_session(db, session_id, after_seq=opening.seq - 1)

    session = events_store.get_session(db, scenario_id, session_id)
    return RewindResponse(
        session=events_store.session_summary(db, session),
        cut_seq=result.cut_seq,
        removed_events=result.removed_events,
        removed_traces=result.removed_traces,
        snapshot_session_id=snapshot_id,
        restored_turn=restored,
    )
