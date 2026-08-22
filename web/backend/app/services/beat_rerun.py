"""Re-run one beat — the engine seam behind *Re-roll*.

The player did not like a line and wants another. The point of this module is that it
re-generates **one beat**, in place, against the context that beat originally saw — rather
than replaying the whole turn, which would move everything after it and cost a full turn's
generations.

Two things make that possible, both built earlier in
``docs/plans/control-over-the-record.md``: the turn engine is split, so
``beat_runner.generate_speaker`` can be called without ``run_turn``; and
``turn_emit.LiveSegment`` can open in **replace mode**, streaming into an existing beat's id
and seq so the re-take lands in the same transcript position.

Takes are kept, not overwritten (``MAX_TAKES``, oldest dropped). The player asked for a
different line, not for the previous one to stop existing — and often the first was better.
They live inside the beat's own row, so one beat keeps one position in the scene however many
times it is re-rolled.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.core.ids import new_id
from app.events.stream import BeatRerollFrame
from app.models import Event, PlaySession, Scenario
from app.schemas.play import TurnRequest
from app.services import beat_runner, session_state, settings_store, turn_setup
from app.services.turn_emit import Emitter, Tracer

#: How many versions of a beat to keep. Five is enough to compare against and small enough
#: that the row stays a row; the oldest is dropped past that.
MAX_TAKES = 5

#: Beat types a re-roll can regenerate. A stat change or a set of choices is not writing.
RERUNNABLE_TYPES = frozenset({"narration", "character_prose", "character_dialogue"})


def _now() -> str:
    return datetime.now(UTC).isoformat()


def record_take(db: Session, row: Event, text: str, *, original: str | None = None) -> dict:
    """Append ``text`` as the newest take and make it active.

    ``data.text`` mirrors the active take so every existing consumer — the buffer, the
    export, reload, the moment prompt — keeps working without knowing takes exist.

    ``original`` must be captured **before** the re-run streams, because the streaming
    segment writes the new wording into ``data.text`` as it closes. Reading it here would
    read the replacement and silently lose the line the player had already read.
    """
    data = dict(row.data) if isinstance(row.data, dict) else {}
    takes = list(data.get("takes") or [])
    if not takes:
        # The beat's original wording becomes take 1, so a re-roll never discards it.
        first = original if original is not None else str(data.get("text") or "")
        if first:
            takes.append({"id": new_id("tk"), "text": first, "ts": _now()})
    takes.append({"id": new_id("tk"), "text": text, "ts": _now()})
    if len(takes) > MAX_TAKES:
        takes = takes[-MAX_TAKES:]
    data["takes"] = takes
    data["activeTake"] = len(takes) - 1
    data["text"] = text
    row.data = data
    db.commit()
    db.refresh(row)
    return data


def set_active_take(db: Session, session_id: str, event_id: str, take: int) -> Event:
    """Flip a beat to one of its kept takes and rebuild the buffer.

    The rebuild matters as much as it does for an edit: without it the cast would go on
    reading whichever take happened to be active when the window was last written.
    """
    row = db.get(Event, event_id)
    if row is None or row.session_id != session_id:
        raise APIError(404, "invalid_reference", "Unknown beat for this play-through.")
    data = dict(row.data) if isinstance(row.data, dict) else {}
    takes = list(data.get("takes") or [])
    if not takes:
        raise APIError(422, "unprocessable", "That beat has only one version.")
    if take < 0 or take >= len(takes):
        raise APIError(
            422, "unprocessable", "That version does not exist.", {"takes": len(takes)}
        )
    data["activeTake"] = take
    data["text"] = str(takes[take].get("text") or "")
    row.data = data
    db.commit()
    db.refresh(row)
    session_state.rebuild_buffer(db, session_id)
    return row


def _preceding_thought(db: Session, session_id: str, row: Event) -> Event | None:
    """The private thought that belonged to this beat, if it had one.

    A character's ``internal_thought`` is emitted immediately before their prose in the same
    turn, so it is the nearest thought row above the beat that has no other beat between
    them. Returning ``None`` when there is none is normal — narrator beats never have one,
    and neither do sessions recorded before thoughts streamed.
    """
    from sqlalchemy import select

    previous = db.scalars(
        select(Event)
        .where(Event.session_id == session_id, Event.seq < row.seq)
        .order_by(Event.seq.desc())
        .limit(1)
    ).first()
    if previous is None or previous.type != "internal_thought":
        return None
    data = previous.data if isinstance(previous.data, dict) else {}
    row_data = row.data if isinstance(row.data, dict) else {}
    if data.get("characterId") != row_data.get("characterId"):
        return None
    return previous


def rerun_beat(
    db: Session, scenario: Scenario, session: PlaySession, row: Event
) -> Iterator[object]:
    """Re-generate one beat in place, streaming the new take into its existing position."""
    if row.type not in RERUNNABLE_TYPES:
        raise APIError(
            422,
            "unprocessable",
            f"A {row.type.replace('_', ' ')} beat cannot be re-rolled.",
            {"type": row.type},
        )

    data = row.data if isinstance(row.data, dict) else {}
    # Captured NOW: the streaming segment rewrites `data.text` when it closes, so reading the
    # original afterwards would read the replacement and lose the take being replaced.
    original_text = str(data.get("text") or "")
    ctx, turn_beats = turn_setup.context_for_replay(
        db, scenario, session.id, through_seq=row.seq - 1
    )
    tracer = Tracer(True, db=None, session_id=session.id, scenario_id=scenario.id, turn=row.seq)
    # `start_seq` is never used in replace mode — the segment carries the row's own seq — but
    # the emitter needs a coherent one in case a consequence block claims an event.
    emitter = Emitter(db, scenario.id, session.id, start_seq=session_state.latest_seq(db, session.id) + 1)
    show_reasoning = settings_store.get_llm(db).reasoning_visibility == "full"

    # Tell the client to clear the beat before the deltas land, or they would append to the
    # take being replaced. A transport frame — nothing about it belongs in the record.
    existing = len(data.get("takes") or []) or 1
    yield BeatRerollFrame(event_id=row.id, take=existing)

    # Each part of the re-generated beat streams back into the row it replaces. The
    # accompanying private thought is replaced too rather than appended: it explained the
    # line that no longer exists, and appending would stack a fresh thought beside a stale
    # one on every re-roll (and grow the transcript each time).
    replace: dict[str, tuple[str, int]] = {row.type: (row.id, row.seq)}
    thought = _preceding_thought(db, session.id, row)
    if thought is not None:
        replace["internal_thought"] = (thought.id, thought.seq)
    consequences: list = []

    if row.type == "narration":
        yield from beat_runner.narrator_interstitial(
            db, ctx, turn_beats, emitter, show_reasoning=show_reasoning, replace=replace
        )
    else:
        speaker = ctx.cast_by_id(str(data.get("characterId") or ""))
        if speaker is None:
            raise APIError(
                422, "unprocessable", "That beat's speaker is no longer in the cast."
            )
        yield from beat_runner.generate_speaker(
            db,
            ctx,
            speaker,
            emitter,
            turn_beats,
            consequences,
            show_reasoning=show_reasoning,
            tracer=tracer,
            replace=replace,
        )

    # Read the new wording back off the row: the segment wrote it there on close, and going
    # through the row rather than holding the text means this works identically whichever
    # generation path produced it.
    db.refresh(row)
    fresh = row.data if isinstance(row.data, dict) else {}
    record_take(db, row, str(fresh.get("text") or ""), original=original_text)
    session_state.rebuild_buffer(db, session.id)


def rerun_turn(
    db: Session, scenario: Scenario, session: PlaySession, row: Event
) -> Iterator[object]:
    """Re-run the whole turn a beat belongs to.

    A beat that went wrong because the *turn* went wrong is not fixed by re-rolling one line
    of it — hence the owner's ask for both scopes. This is deliberately a **composition** of
    machinery that already exists rather than new engine code: find the turn boundary,
    truncate back to it, and replay the player's persisted line through the ordinary loop.

    The previous version is not kept as a take here. A turn re-run replaces several beats,
    and a per-beat pager cannot express "these four lines, or those four" — the way to keep
    the old version of a whole turn is to branch before re-running it.
    """
    from app.services import turn_engine  # local: turn_engine imports this module's siblings

    opening = session_state.turn_boundary(db, session.id, row.id)
    data = opening.data if isinstance(opening.data, dict) else {}

    session_state.truncate_session(db, session.id, after_seq=opening.seq - 1)

    replay = TurnRequest(
        session_id=session.id,
        text=str(data.get("text") or ""),
        directed_at=data.get("directedAt"),
        pov_character_id=data.get("pov"),
        guidance=data.get("guidance"),
        tagged_doc_ids=list(data.get("taggedDocIds") or []),
        continuation=not str(data.get("text") or "").strip(),
        trace=True,
    )
    yield from turn_engine.run_turn(db, scenario, replay)
