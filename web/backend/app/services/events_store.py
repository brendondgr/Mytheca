"""Event + play-session persistence for the turn loop.

The durable side of the turn loop: resolve/create the :class:`PlaySession`, assign
the per-session monotonic ``seq`` (``max(seq)+1``, with the
``(session_id, seq)`` unique constraint as the hard backstop), record the player's
``user_turn``, and persist each emitted story event so the row id matches the id
streamed to the client.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.events.envelope import StoryEvent
from app.events.stream import TurnTraceFrame
from app.models import Event, PlaySession, TurnTrace


def next_seq(db: Session, session_id: str) -> int:
    """Return the next monotonic ``seq`` for a session (``max(seq)+1``, 0 if empty)."""
    current = db.scalar(select(func.max(Event.seq)).where(Event.session_id == session_id))
    return 0 if current is None else int(current) + 1


def create_session(db: Session, scenario_id: str) -> PlaySession:
    """Open a new play session for a scenario."""
    session = PlaySession(scenario_id=scenario_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def resolve_session(db: Session, scenario_id: str, session_id: str | None) -> PlaySession:
    """Return the requested session (validated against the scenario) or open a new one."""
    if not session_id:
        return create_session(db, scenario_id)
    session = db.get(PlaySession, session_id)
    if session is None:
        raise APIError(404, "invalid_reference", "Unknown play session.")
    if session.scenario_id != scenario_id:
        raise APIError(400, "bad_request", "Session does not belong to this scenario.")
    return session


def record_user_turn(
    db: Session,
    *,
    scenario_id: str,
    session_id: str,
    seq: int,
    text: str,
    directed_at: str | None,
) -> Event:
    """Persist the player's input as a ``user_turn`` event (not part of the output stream)."""
    event = Event(
        type="user_turn",
        seq=seq,
        scenario_id=scenario_id,
        session_id=session_id,
        visibility="public",
        data={"text": text, "directedAt": directed_at},
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _parse_ts(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):  # pragma: no cover - defensive
        return datetime.now(UTC)


def persist_story_event(db: Session, event: StoryEvent) -> Event:
    """Persist a validated story event, keeping the row id == streamed event id."""
    data: dict[str, Any] = event.data.model_dump(mode="json", by_alias=True)
    row = Event(
        id=event.id,
        type=event.type,
        seq=event.seq,
        scenario_id=event.scenario_id,
        session_id=event.session_id,
        ts=_parse_ts(event.ts),
        visibility=event.visibility,
        data=data,
    )
    db.add(row)
    db.commit()
    return row


def persist_trace(
    db: Session,
    *,
    session_id: str,
    scenario_id: str,
    turn: int,
    frame: TurnTraceFrame,
) -> None:
    """Persist one diagnostic trace step so a scene's graph/RAG activity survives review.

    Best-effort: a trace write must never break the turn stream, so a failure is rolled
    back and swallowed (the frame still streamed to the player). Ordered by ``(turn, n)``.
    """
    try:
        db.add(
            TurnTrace(
                session_id=session_id,
                scenario_id=scenario_id,
                turn=turn,
                n=frame.n,
                step=frame.step,
                title=frame.title,
                detail=frame.detail,
                data=frame.data,
            )
        )
        db.commit()
    except Exception:  # pragma: no cover - defensive; diagnostics are non-critical
        db.rollback()


def touch_session(db: Session, session_id: str) -> None:
    """Bump a session's ``updated_at`` so resume can pick the most recent play-through."""
    session = db.get(PlaySession, session_id)
    if session is None:  # pragma: no cover - defensive
        return
    session.updated_at = datetime.now(UTC)
    db.commit()
