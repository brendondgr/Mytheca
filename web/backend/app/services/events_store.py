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
    pov: str | None = None,
) -> Event:
    """Persist the player's input as a ``user_turn`` event (not part of the output stream).

    ``pov`` is the Player POV character id the line was spoken *as* (``None`` = the
    default guide/narrator behavior). It is carried on the row so reload can faithfully
    reproduce the line as that character's beat rather than a left-side player beat.
    """
    event = Event(
        type="user_turn",
        seq=seq,
        scenario_id=scenario_id,
        session_id=session_id,
        visibility="public",
        data={"text": text, "directedAt": directed_at, "pov": pov},
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


def get_session(db: Session, scenario_id: str, session_id: str) -> PlaySession:
    """Return the session (validated against the scenario) or raise 404/400."""
    session = db.get(PlaySession, session_id)
    if session is None:
        raise APIError(404, "invalid_reference", "Unknown play session.")
    if session.scenario_id != scenario_id:
        raise APIError(400, "bad_request", "Session does not belong to this scenario.")
    return session


def list_sessions(db: Session, scenario_id: str) -> list[PlaySession]:
    """All play sessions for a scenario, most-recently-played first (resume order)."""
    return list(
        db.scalars(
            select(PlaySession)
            .where(PlaySession.scenario_id == scenario_id)
            .order_by(PlaySession.updated_at.desc(), PlaySession.created_at.desc())
        )
    )


def latest_session(db: Session, scenario_id: str) -> PlaySession | None:
    """The most-recently-played session for a scenario, or ``None`` if never played."""
    return next(iter(list_sessions(db, scenario_id)), None)


def session_events(db: Session, session_id: str) -> list[Event]:
    """Every persisted event for a session, in ``seq`` order (incl. hidden thoughts +
    the ``user_turn`` rows) — the source for both reload and export."""
    return list(
        db.scalars(
            select(Event).where(Event.session_id == session_id).order_by(Event.seq)
        )
    )


def ended_on_a_question(db: Session, session_id: str, *, before_seq: int | None = None) -> bool:
    """True when the PREVIOUS turn ended on the planner's own question to the player.

    The planner may ask the player where the story should go, but never twice running — a
    scene that only asks has stopped being a scene. Its question is by construction the
    final event of the turn that asked it (the engine breaks the beat loop and suppresses
    both the holding narration and the ordinary follow-up suggestions), so one row answers
    this.

    ``before_seq`` is the seq the current turn starts writing at: by the time the engine
    needs this, the player's own ``user_turn`` row is already persisted, so "the last
    event" would be that line rather than the answer to it.
    """
    q = select(Event).where(Event.session_id == session_id)
    if before_seq is not None:
        q = q.where(Event.seq < before_seq)
    row = db.scalars(q.order_by(Event.seq.desc()).limit(1)).first()
    if row is None or row.type != "branch_choices":
        return False
    data = row.data if isinstance(row.data, dict) else {}
    return bool(str(data.get("prompt") or "").strip())


def session_traces(db: Session, session_id: str) -> list[TurnTrace]:
    """Every persisted diagnostic trace step for a session, ordered by ``(turn, n)``."""
    return list(
        db.scalars(
            select(TurnTrace)
            .where(TurnTrace.session_id == session_id)
            .order_by(TurnTrace.turn, TurnTrace.n)
        )
    )


def user_turn_stats(db: Session, session_id: str) -> tuple[int, str]:
    """``(turn_count, preview)`` for a session — the number of player turns and the
    first player line (a human label for the play-through in the resume list)."""
    rows = list(
        db.scalars(
            select(Event)
            .where(Event.session_id == session_id, Event.type == "user_turn")
            .order_by(Event.seq)
        )
    )
    preview = str(rows[0].data.get("text", "")) if rows else ""
    return len(rows), preview


def close_session(db: Session, session_id: str) -> PlaySession:
    """Mark a session closed (the save-on-close signal); idempotent, bumps recency."""
    session = db.get(PlaySession, session_id)
    if session is None:  # pragma: no cover - guarded by the route
        raise APIError(404, "invalid_reference", "Unknown play session.")
    now = datetime.now(UTC)
    session.closed_at = now
    session.updated_at = now
    db.commit()
    return session
