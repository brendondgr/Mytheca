"""Turn engine — the runtime story loop.

Drives one player turn: persist the ``user_turn``, then emit the bot's typed story
events, validating + persisting each and streaming the visible ones as NDJSON.

This phase (P1) emits a deterministic **echo** set (narration + a single character's
action/line) to prove the transport end to end; the real per-character POV
think→speak generation replaces ``_echo_turn`` in later phases. ``_Emitter``
centralizes the seq + persist + buffer + withhold-hidden plumbing every phase reuses.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.events.envelope import StoryEvent
from app.events.stream import build_event
from app.memory import buffer
from app.models import Character, Scenario, Setting
from app.schemas.base import EventType, Visibility
from app.schemas.play import TurnRequest
from app.services import crud, events_store


class _Emitter:
    """Assigns the per-session ``seq``, persists every event, mirrors visible prose
    into the recent-turn buffer, and **withholds hidden events** from the stream."""

    def __init__(self, db: Session, scenario_id: str, session_id: str, start_seq: int) -> None:
        self._db = db
        self._scenario_id = scenario_id
        self._session_id = session_id
        self._seq = start_seq

    def emit(
        self,
        type_: EventType,
        data: dict[str, Any],
        *,
        visibility: Visibility | None = None,
        buffer_role: str | None = None,
        character_id: str | None = None,
    ) -> Iterator[StoryEvent]:
        """Build → persist → (buffer) → yield (unless hidden). One event, one seq."""
        event = build_event(
            type_,
            data,
            scenario_id=self._scenario_id,
            session_id=self._session_id,
            seq=self._seq,
            visibility=visibility,
        )
        self._seq += 1
        events_store.persist_story_event(self._db, event)
        if buffer_role:
            buffer.push_turn(
                self._session_id, buffer_role, str(data.get("text", "")), character_id=character_id
            )
        if event.visibility != "hidden":
            yield event


def validate_turn_inputs(db: Session, scenario_id: str, req: TurnRequest) -> Scenario:
    """Pre-flight (before the 200 stream opens): scenario exists, text present, session valid."""
    scenario = crud.get_scenario(db, scenario_id)  # raises 404 when missing
    if not (req.text or "").strip():
        raise APIError(400, "bad_request", "Turn text is required.")
    if req.session_id:
        events_store.resolve_session(db, scenario_id, req.session_id)  # validates only
    return scenario


def run_turn(db: Session, scenario: Scenario, req: TurnRequest) -> Iterator[StoryEvent]:
    """Run one turn, yielding the visible story events in order."""
    session = events_store.resolve_session(db, scenario.id, req.session_id)
    text = (req.text or "").strip()

    seq0 = events_store.next_seq(db, session.id)
    events_store.record_user_turn(
        db,
        scenario_id=scenario.id,
        session_id=session.id,
        seq=seq0,
        text=text,
        directed_at=req.directed_at,
    )
    buffer.push_turn(session.id, "player", text)

    emitter = _Emitter(db, scenario.id, session.id, start_seq=seq0 + 1)
    yield from _echo_turn(db, scenario, req, text, emitter)


def _echo_turn(
    db: Session,
    scenario: Scenario,
    req: TurnRequest,
    text: str,
    emitter: _Emitter,
) -> Iterator[StoryEvent]:
    """Deterministic placeholder beat (replaced by real generation in P3+)."""
    setting_name = _setting_name(db, scenario)
    yield from emitter.emit(
        "narration",
        {"text": f"The {setting_name} stills as your words settle.", "done": True},
        buffer_role="narrator",
    )

    speaker = _echo_speaker(db, scenario, req.directed_at)
    if speaker is not None:
        cid, name = speaker
        yield from emitter.emit(
            "character_action",
            {"characterId": cid, "text": f"{name} weighs you for a moment, then meets your eyes."},
            buffer_role="character",
            character_id=cid,
        )
        yield from emitter.emit(
            "character_dialogue",
            {"characterId": cid, "text": f"You said: “{text}”", "done": True},
            buffer_role="character",
            character_id=cid,
        )


def _setting_name(db: Session, scenario: Scenario) -> str:
    if scenario.setting_id:
        setting = db.get(Setting, scenario.setting_id)
        if setting is not None:
            return setting.name
    return "room"


def _echo_speaker(db: Session, scenario: Scenario, directed_at: str | None) -> tuple[str, str] | None:
    """Pick the echo speaker: the addressed cast member, else the first cast member."""
    cast: list[str] = list(scenario.cast_ids or [])
    candidate = directed_at if (directed_at and directed_at in cast) else (cast[0] if cast else None)
    if candidate is None:
        return None
    char = db.get(Character, candidate)
    if char is None:  # dangling soft-ref (deleted character) — skip gracefully
        return None
    return char.id, char.name
