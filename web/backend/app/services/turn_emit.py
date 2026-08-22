"""Turn emission — the seq/persist/buffer plumbing every phase of a turn reuses.

Split out of ``turn_engine`` so a **single beat** can be re-emitted without replaying a
whole turn (``docs/plans/control-over-the-record.md``). Nothing here decides *what* happens
in a scene; it owns the mechanics of getting a decided beat onto the wire and into Postgres:

* :class:`Emitter` — assign the next ``seq``, build and validate the envelope, persist the
  row so its id matches the streamed id, push prose into the recent-turn buffer, and
  withhold anything hidden from the visible stream.
* :class:`LiveSegment` — accumulate a delta-streamed passage so the same event id + seq can
  be re-emitted with incremental text until the final ``done`` frame.
* :class:`Tracer` — the diagnostic trace steps, streamed when the client opted in and
  persisted either way.

This is a **pure move**: the three classes are unchanged apart from losing the leading
underscore, which they carried only because they used to be private to one module.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.events.envelope import StoryEvent
from app.events.stream import TurnTraceFrame, build_event, chunk_text
from app.memory import buffer
from app.schemas.base import EventType, Visibility
from app.models import Event
from app.services import events_store


class Emitter:
    """Assigns the per-session ``seq``, persists every event, mirrors visible prose
    into the recent-turn buffer, and **withholds hidden events** from the stream."""

    def __init__(self, db: Session, scenario_id: str, session_id: str, start_seq: int) -> None:
        self._db = db
        self._scenario_id = scenario_id
        self._session_id = session_id
        self._seq = start_seq

    # -- shared plumbing for the live streamer ------------------------------

    @property
    def scenario_id(self) -> str:
        return self._scenario_id

    @property
    def session_id(self) -> str:
        return self._session_id

    def take_seq(self) -> int:
        """Claim the next sequence number (one per event, streamed or not)."""
        seq = self._seq
        self._seq += 1
        return seq

    def build_full(
        self,
        type_: EventType,
        text: str,
        *,
        event_id: str,
        seq: int,
        character_id: str | None,
        visibility: Visibility | None,
    ) -> StoryEvent:
        """The DB-authoritative row for a streamed event: the whole text, ``done``."""
        data: dict[str, Any] = {"text": text, "done": True}
        if character_id is not None:
            data["characterId"] = character_id
        return build_event(
            type_,
            data,
            scenario_id=self._scenario_id,
            session_id=self._session_id,
            seq=seq,
            event_id=event_id,
            visibility=visibility,
        )

    def update_text(self, event_id: str, text: str) -> None:
        """Rewrite an existing row's ``text`` in place — the re-roll path.

        Deliberately does **not** touch the recent-turn buffer: a re-roll rewrites one beat
        in the middle of a session, and pushing the new text would append it to the end of
        the window rather than replacing it where it sits. The caller rebuilds the whole
        buffer from the rows afterwards, which is the only way to get that right.
        """
        row = self._db.get(Event, event_id)
        if row is None:  # pragma: no cover - defensive
            return
        data = dict(row.data) if isinstance(row.data, dict) else {}
        data["text"] = text
        row.data = data
        self._db.commit()

    def persist(
        self, event: StoryEvent, *, buffer_role: str | None, character_id: str | None
    ) -> None:
        """Write the row and mirror visible prose into the recent-turn buffer."""
        events_store.persist_story_event(self._db, event)
        if buffer_role:
            buffer.push_turn(
                self._session_id,
                buffer_role,
                str(getattr(event.data, "text", "") or ""),
                character_id=character_id,
            )

    def open_stream(
        self,
        type_: EventType,
        *,
        character_id: str | None = None,
        visibility: Visibility | None = None,
        buffer_role: str | None = None,
        replace: tuple[str, int] | None = None,
    ) -> "LiveSegment":
        """Start streaming one event; the caller drives it with ``delta``/``close``.

        ``replace`` is the re-roll path: give it an existing ``(event_id, seq)`` and the
        segment streams into that beat's position and updates its row instead of inserting.
        """
        return LiveSegment(
            self,
            type_,
            character_id=character_id,
            visibility=visibility,
            buffer_role=buffer_role,
            replace=replace,
        )

    def emit(
        self,
        type_: EventType,
        data: dict[str, Any],
        *,
        visibility: Visibility | None = None,
        buffer_role: str | None = None,
        character_id: str | None = None,
    ) -> Iterator[StoryEvent]:
        """Build → persist → (buffer) → yield (unless hidden). One full event, one seq."""
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

    def emit_streamed(
        self,
        type_: EventType,
        text: str,
        *,
        character_id: str | None = None,
        buffer_role: str | None = None,
    ) -> Iterator[StoryEvent]:
        """Delta-stream a visible prose event: persist the full text once, then yield
        incremental same-id/same-seq chunks (``done: false`` until the final chunk)."""
        event_id = new_id("ev")
        seq = self._seq
        self._seq += 1

        full_data: dict[str, Any] = {"text": text, "done": True}
        if character_id is not None:
            full_data["characterId"] = character_id
        full = build_event(
            type_,
            full_data,
            scenario_id=self._scenario_id,
            session_id=self._session_id,
            seq=seq,
            event_id=event_id,
        )
        events_store.persist_story_event(self._db, full)
        if buffer_role:
            buffer.push_turn(self._session_id, buffer_role, text, character_id=character_id)

        chunks = chunk_text(text)
        for i, chunk in enumerate(chunks):
            data: dict[str, Any] = {"text": chunk, "done": i == len(chunks) - 1}
            if character_id is not None:
                data["characterId"] = character_id
            yield build_event(
                type_,
                data,
                scenario_id=self._scenario_id,
                session_id=self._session_id,
                seq=seq,
                event_id=event_id,
            )


class LiveSegment:
    """One event id being streamed live, so deltas can be emitted as text arrives.

    :meth:`Emitter.emit_streamed` persists a finished string and replays it as fake
    deltas; this is the real thing — the row is written on :meth:`close`, once the text
    is actually complete, and every delta before that goes straight to the wire.
    """

    def __init__(
        self,
        emitter: "Emitter",
        type_: EventType,
        *,
        character_id: str | None,
        visibility: Visibility | None,
        buffer_role: str | None,
        replace: tuple[str, int] | None = None,
    ) -> None:
        self._emitter = emitter
        self._type = type_
        self._character_id = character_id
        self._visibility = visibility
        self._buffer_role = buffer_role
        # **Replace mode** (a re-roll): stream into an EXISTING beat's id and seq instead of
        # claiming new ones, so the re-take lands in the same transcript position and `close`
        # updates that row rather than inserting a second one. Taking a new seq here is what
        # would push the re-rolled beat to the end of the scene.
        self._replacing = replace is not None
        self._event_id, self._seq = replace if replace else (new_id("ev"), emitter.take_seq())
        self._text = ""
        self._closed = False

    @property
    def text(self) -> str:
        """Everything streamed for this event so far."""
        return self._text

    def delta(self, chunk: str) -> Iterator[StoryEvent]:
        """Stream one increment of this event's text."""
        if not chunk:
            return
        self._text += chunk
        yield from self._frame(chunk, done=False)

    def close(self) -> Iterator[StoryEvent]:
        """Persist the finished text, mirror it into the buffer, and send the last frame."""
        if self._closed:
            return
        self._closed = True
        full = self._emitter.build_full(
            self._type,
            self._text,
            event_id=self._event_id,
            seq=self._seq,
            character_id=self._character_id,
            visibility=self._visibility,
        )
        if self._replacing:
            # The row already exists; its `takes` bookkeeping belongs to the caller, which
            # knows this is a re-roll. Persisting again would violate (session_id, seq).
            self._emitter.update_text(self._event_id, self._text)
        else:
            self._emitter.persist(
                full, buffer_role=self._buffer_role, character_id=self._character_id
            )
        yield from self._frame("", done=True)

    def _frame(self, chunk: str, *, done: bool) -> Iterator[StoryEvent]:
        data: dict[str, Any] = {"text": chunk, "done": done}
        if self._character_id is not None:
            data["characterId"] = self._character_id
        event = build_event(
            self._type,
            data,
            scenario_id=self._emitter.scenario_id,
            session_id=self._emitter.session_id,
            seq=self._seq,
            event_id=self._event_id,
            visibility=self._visibility,
        )
        if event.visibility != "hidden":
            yield event


class Tracer:
    """Interleaves diagnostic :class:`TurnTraceFrame`s and **persists** every step.

    Two independent concerns: the ``enabled`` flag governs whether a frame is *streamed*
    to the client (off by default, so the default stream and the story-event contract are
    unchanged); persistence happens **regardless** (best-effort, when a db context is
    given) so a scene's graph/RAG activity survives for later review and export. It stamps
    a per-turn ordinal ``n`` so the Inspector — and the reload/export — can render the
    steps in the exact order they happened.
    """

    def __init__(
        self,
        enabled: bool,
        *,
        db: Session | None = None,
        session_id: str | None = None,
        scenario_id: str | None = None,
        turn: int = 0,
    ) -> None:
        self._enabled = enabled
        self._n = 0
        self._db = db
        self._session_id = session_id
        self._scenario_id = scenario_id
        self._turn = turn

    def emit(
        self,
        step: str,
        title: str,
        *,
        detail: str = "",
        data: dict[str, Any] | None = None,
    ) -> Iterator[TurnTraceFrame]:
        self._n += 1
        frame = TurnTraceFrame(n=self._n, step=step, title=title, detail=detail, data=data or {})
        if self._db is not None and self._session_id and self._scenario_id:
            events_store.persist_trace(
                self._db,
                session_id=self._session_id,
                scenario_id=self._scenario_id,
                turn=self._turn,
                frame=frame,
            )
        if self._enabled:
            yield frame

