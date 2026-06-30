"""Turn engine — the runtime story loop.

Drives one player turn: persist the ``user_turn``, assemble Band-1 context, run the
per-character POV loop (one isolated LLM call per active speaker), and stream the
visible story events as NDJSON while persisting each.

Visible prose (``narration`` / ``character_dialogue``) **delta-streams**: the same
event (same id + seq) is emitted with incremental ``text`` + ``done: false`` until the
last chunk sets ``done: true`` (the client accumulates by id; the persisted row holds
the full text). ``character_action`` streams as one full event; ``internal_thought``
(``visibility: hidden``) is persisted but withheld. ``_Emitter`` centralizes the
seq + persist + buffer + withhold-hidden plumbing every phase reuses.

This phase (P3) generates a single speaker (the addressed cast member, else the first);
the reasoned Director / multi-speaker queue replaces ``_pick_speaker`` in later phases.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy.orm import Session

from app.agents import character_turn_agent, director_agent, narrator_agent
from app.core.errors import APIError
from app.core.ids import new_id
from app.events.envelope import StoryEvent
from app.events.stream import build_event, chunk_text
from app.memory import buffer
from app.models import Scenario
from app.schemas.base import EventType, Visibility
from app.schemas.play import TurnRequest
from app.services import assembler, crud, emission, events_store, turn_writer
from app.services.assembler import CastMember, TurnContext
from app.services.turn_writer import Consequence


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

    # Assemble against committed history, THEN push the player's line so it becomes
    # history for the next turn (the current line also seeds this turn's transcript,
    # so it is present even when the buffer is disabled).
    ctx = assembler.assemble_context(db, scenario, session.id, req.directed_at, player_text=text)
    buffer.push_turn(session.id, "player", text)

    emitter = _Emitter(db, scenario.id, session.id, start_seq=seq0 + 1)
    # The chronological this-turn transcript handed to each speaker so a later speaker
    # genuinely reacts to its predecessor (sequential by nature — §9).
    turn_beats: list[dict] = [{"role": "player", "text": text, "characterId": None}]

    # Durable consequences implied by the turn (populated from state_update events in
    # the branch/stat phase); routed off the hot path by the cold-path turn-writer.
    consequences: list[Consequence] = []

    decision = director_agent.who_is_up(db, ctx)
    speakers = [m for cid in decision.speakers if (m := ctx.cast_by_id(cid)) is not None]
    if not speakers:
        yield from emitter.emit(
            "narration", {"text": "The scene waits, quiet.", "done": True}, buffer_role="narrator"
        )
        return

    for _index, speaker in enumerate(speakers):
        # Narrator Mode: a transition beat before the speaker (POV Mode: off — D1).
        if req.mode == "narrator":
            yield from _narrator_interstitial(db, ctx, turn_beats, emitter)
        yield from _generate_speaker(db, ctx, speaker, emitter, turn_beats)

    # Cold path (Band 3): runs after the last event is yielded — never blocks the
    # player, best-effort, no-op when there are no consequences or the graph is down.
    turn_writer.write_turn(
        db,
        scenario=scenario,
        session_id=session.id,
        turn_seq=seq0,
        summary=_turn_summary(turn_beats),
        consequences=consequences,
    )


def _turn_summary(turn_beats: list[dict]) -> str:
    """A one-line summary of the turn for the appended :Event node."""
    parts = [str(b.get("text", "")).strip() for b in turn_beats if b.get("text")]
    return " · ".join(parts)[:240]


def _narrator_interstitial(
    db: Session,
    ctx: TurnContext,
    turn_beats: list[dict],
    emitter: _Emitter,
) -> Iterator[StoryEvent]:
    """Emit an optional narrator beat (Narrator Mode); skip silently on failure."""
    text = narrator_agent.interstitial(db, ctx, turn_beats)
    if not text:
        return
    yield from emitter.emit_streamed("narration", text, buffer_role="narrator")
    turn_beats.append({"role": "narrator", "text": text, "characterId": None})


def _generate_speaker(
    db: Session,
    ctx: TurnContext,
    speaker: CastMember,
    emitter: _Emitter,
    turn_beats: list[dict],
) -> Iterator[StoryEvent]:
    """Generate one speaker's beat, emit its events, and append them to ``turn_beats``."""
    raw = character_turn_agent.generate_line(db, ctx, speaker, turn_beats=turn_beats)
    roster = {i + 1: m.id for i, m in enumerate(ctx.cast)}
    for seg in emission.parse_emission(raw, roster=roster, fallback_speaker_id=speaker.id):
        if seg.type == "internal_thought":
            # Hidden conditioning — persisted, withheld, and NOT shown to later speakers.
            yield from emitter.emit(
                "internal_thought",
                {"characterId": seg.character_id, "text": seg.text},
                visibility="hidden",
            )
        elif seg.type == "character_action":
            yield from emitter.emit(
                "character_action",
                {"characterId": seg.character_id, "text": seg.text},
                buffer_role="character",
                character_id=seg.character_id,
            )
            turn_beats.append({"role": "character", "text": seg.text, "characterId": seg.character_id})
        elif seg.type == "character_dialogue":
            yield from emitter.emit_streamed(
                "character_dialogue",
                seg.text,
                character_id=seg.character_id,
                buffer_role="character",
            )
            turn_beats.append({"role": "character", "text": seg.text, "characterId": seg.character_id})
