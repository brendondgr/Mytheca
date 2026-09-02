"""Play route — submit a turn, stream the story events back as NDJSON.

``POST /api/play/{scenarioId}/turn`` runs the turn and returns the event stream in
its response body (``application/x-ndjson``), reusing the build/triage streaming
pattern: pre-flight failures (unknown scenario, empty text, bad session) return a
normal error envelope *before* the 200 stream opens; a mid-stream failure is the
terminal ``error`` frame.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import APIError
from app.events.stream import TurnErrorFrame, build_event, to_ndjson_line, with_keepalive
from app.models import Character, Event, PlaySession, Scenario
from app.schemas.memory import (
    BeatMemoryResponse,
    MemoryContradiction,
    RecalledMemory,
)
from app.schemas.play import (
    MomentRequest,
    MomentStageFrame,
    PersistedEvent,
    PersistedTrace,
    PresenceRequest,
    SessionHistoryResponse,
    RecapRequest,
    RecapResponse,
    SceneKnowledgeResponse,
    SessionListResponse,
    SessionSummary,
    StandingDirectionRequest,
    StandingDirectionResponse,
    StandingItem,
    TurnRequest,
)
from app.services import (
    crud,
    direction_runtime,
    events_store,
    history_compaction,
    graph_reader,
    memory_store,
    presence,
    scene_knowledge,
    scene_moment,
    session_export,
    turn_engine,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/play", tags=["play"])

# Keep proxies (nginx) from buffering the live stream (mirrors the build/triage routes).
_STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _summary(db: Session, session: PlaySession) -> SessionSummary:
    """Thin alias — the shape lives in ``events_store`` so ``play_record`` renders the
    identical summary (including the lineage fields)."""
    return events_store.session_summary(db, session)


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
            # ...but do not lose it either: without this, an ordinary bug in the turn loop
            # is indistinguishable from a model failure, because both reach the player as
            # the same opaque sentence and nothing is written to the server log.
            logger.exception("Turn failed (scenario=%s)", scenario_id)
            yield to_ndjson_line(TurnErrorFrame(message="The turn failed unexpectedly."))

    return StreamingResponse(_lines(), media_type="application/x-ndjson", headers=_STREAM_HEADERS)


@router.post("/{scenario_id}/moment/stream")
def play_moment(scenario_id: str, data: MomentRequest, db: Session = Depends(get_db)):
    """Capture the scene as a picture; stream the two stages, then the persisted beat.

    The player's **Create image** action. Frames: ``moment_stage`` (``prompt`` →
    ``render``, the latter re-emitted as the keep-alive heartbeat while ComfyUI
    works), then the ``scene_image`` story event, or a terminal ``error`` frame.
    Everything knowable up front — unknown scenario/session, an unplayed scene, an
    unconfigured ComfyUI or model — is a normal error envelope before the 200 opens.
    """
    ctx = scene_moment.prepare_moment(db, scenario_id, data)
    # The heartbeat has to say what is ACTUALLY happening: writing the prompt takes as
    # long as the render on a local reasoning model, and a "still painting" tick during
    # the prompt stage would name the wrong half of the work. Single writer (the worker
    # thread yielding frames), single reader (the keep-alive callback).
    current: dict[str, str] = {"stage": "prompt"}
    heartbeat = {"prompt": "Still reading the scene…", "render": "Still painting…"}

    def _tracked() -> Iterator:
        for frame in scene_moment.generate_moment(
            db, ctx, prompt=data.prompt, negative=data.negative, style=data.art_style
        ):
            if isinstance(frame, MomentStageFrame):
                current["stage"] = frame.stage
            yield frame

    def _lines() -> Iterator[str]:
        try:
            for frame in with_keepalive(
                _tracked(),
                lambda: MomentStageFrame(
                    stage=current["stage"],  # type: ignore[arg-type]  # only ever a valid stage
                    message=heartbeat[current["stage"]],
                ),
            ):
                yield to_ndjson_line(frame)
        except APIError as exc:
            yield to_ndjson_line(TurnErrorFrame(message=exc.message))
        except Exception:  # never leak a stack trace into the stream
            logger.exception("Scene image failed (scenario=%s)", scenario_id)
            yield to_ndjson_line(TurnErrorFrame(message="The image could not be generated."))

    return StreamingResponse(_lines(), media_type="application/x-ndjson", headers=_STREAM_HEADERS)


@router.post("/{scenario_id}/presence", response_model=PersistedEvent)
def set_presence(scenario_id: str, data: PresenceRequest, db: Session = Depends(get_db)):
    """Manually set a character's scene presence (the cast-rail control + its undo).

    Persists a ``character_status_change`` event (``auto=False``) on the session, so the
    change folds into ``presence.current_presence`` exactly like an engine-driven one and
    survives reload. Undo is just the inverse call (the client posts the prior status)."""
    scenario = crud.get_scenario(db, scenario_id)  # 404 when unknown
    session = events_store.get_session(db, scenario_id, data.session_id)  # 404/400
    status = presence.normalize_status(data.status)
    if status is None:
        raise APIError(400, "bad_request", "Unknown presence status.")
    # The authored roster, or anyone else in this storyline — a scene can gain a guest
    # mid-play (the cast rail's "Elsewhere in the world", or an accepted `cast_request`).
    # The scenario row is never mutated: the guest belongs to this play-through. A character
    # from a DIFFERENT storyline is still a 404 — presence must not be a way to smuggle
    # someone in from another world.
    if data.character_id not in (scenario.cast_ids or []):
        guest = db.get(Character, data.character_id) if data.character_id else None
        if guest is None or guest.storyline_id != scenario.storyline_id:
            raise APIError(404, "invalid_reference", "Character is not in this world.")
    event = build_event(
        "character_status_change",
        {"characterId": data.character_id, "status": status, "reason": data.reason, "auto": False},
        scenario_id=scenario_id,
        session_id=session.id,
        seq=events_store.next_seq(db, session.id),
    )
    events_store.persist_story_event(db, event)
    events_store.touch_session(db, session.id)
    return PersistedEvent(
        type=event.type,
        id=event.id,
        seq=event.seq,
        scenario_id=event.scenario_id,
        session_id=event.session_id,
        ts=event.ts,  # type: ignore[arg-type]  # ISO string coerced to datetime by pydantic
        visibility=event.visibility,
        data=event.data.model_dump(by_alias=True),
    )


@router.get("/{scenario_id}/relationships")
def scenario_relationships(scenario_id: str, db: Session = Depends(get_db)):
    """The scenario's live character↔character relationships from the story graph.

    Best-effort: an empty list when the graph is off/unreachable (the story player then
    keeps its seed placeholder). 404 only when the scenario itself is unknown.

    ``graphAvailable`` distinguishes the two reasons the list can be empty — "this world has
    no relationships yet" from "there is no graph on this install". They look identical from
    the list alone, and the difference decides whether the scene's **Ties** control is a
    setting worth offering or a control that would silently do nothing.
    """
    crud.get_scenario(db, scenario_id)  # 404 when the scenario is unknown
    return {
        "relationships": graph_reader.scenario_relationships(db, scenario_id),
        "graphAvailable": bool(graph_reader.scenario_graph(db, scenario_id).get("available")),
    }


@router.get("/{scenario_id}/sessions", response_model=SessionListResponse)
def list_sessions(scenario_id: str, db: Session = Depends(get_db)):
    """Every saved play-through of a scenario, most-recently-played first (resume list)."""
    crud.get_scenario(db, scenario_id)  # 404 when the scenario is unknown
    sessions = events_store.list_sessions(db, scenario_id)
    return SessionListResponse(sessions=[_summary(db, s) for s in sessions])


@router.get("/{scenario_id}/sessions/{session_id}", response_model=SessionHistoryResponse)
def session_history(scenario_id: str, session_id: str, db: Session = Depends(get_db)):
    """The full record of one play-through — metadata + every event (incl. hidden
    thoughts + the ``user_turn`` rows) + every diagnostic trace step — so the story
    player can rehydrate the transcript, thoughts, stats, and graph/RAG activity."""
    crud.get_scenario(db, scenario_id)
    session = events_store.get_session(db, scenario_id, session_id)  # 404/400
    events = events_store.session_events(db, session_id)
    traces = events_store.session_traces(db, session_id)
    return SessionHistoryResponse(
        session=_summary(db, session),
        events=[
            PersistedEvent(
                type=e.type,
                id=e.id,
                seq=e.seq,
                scenario_id=e.scenario_id,
                session_id=e.session_id,
                ts=e.ts,
                visibility=e.visibility,  # type: ignore[arg-type]
                data=e.data,
            )
            for e in events
        ],
        traces=[
            PersistedTrace(
                turn=t.turn, n=t.n, step=t.step, title=t.title, detail=t.detail, data=t.data
            )
            for t in traces
        ],
        standing_direction=_standing(session),
    )


def _standing(session) -> list[StandingItem]:
    """The session's outstanding direction, in wire shape.

    Read through ``direction_runtime.load_standing`` rather than off the column directly, so
    the one place that tolerates a malformed row is the same one the turn loop uses.
    """
    return [
        StandingItem(
            id=r.id, text=r.text, actor_id=r.actor_id, pinned=r.pinned, from_turn=r.from_turn
        )
        for r in direction_runtime.load_standing(session)
    ]


@router.get(
    "/{scenario_id}/sessions/{session_id}/beats/{event_id}/memory",
    response_model=BeatMemoryResponse,
)
def beat_memory(
    scenario_id: str, session_id: str, event_id: str, db: Session = Depends(get_db)
):
    """The memories one beat was written with — the player-facing "where did this come from?".

    Reads the ids stamped on the beat's own ``Event.data`` when it was streamed, so it costs
    the turn path nothing and works on a reopened scene. A beat with no memory behind it
    returns an **empty list, not a 404**: "this line came from nowhere in particular" is a
    real and common answer, and the caller should not have to treat it as an error.

    Deliberately player-facing. Scores, fade multipliers and cue hits are not here — those
    are engine internals and the Turn Inspector already shows them.
    """
    crud.get_scenario(db, scenario_id)
    events_store.get_session(db, scenario_id, session_id)  # 404/400
    row = db.get(Event, event_id)
    if row is None or row.session_id != session_id:
        raise APIError(404, "not_found", "No such beat in this play-through.")

    ids = [str(i) for i in ((row.data or {}).get("recalled") or [])]
    memories = memory_store.by_ids(db, ids)
    if not memories:
        return BeatMemoryResponse(eventId=event_id, memories=[])

    names = {c.id: c.name for c in db.query(Character).all()}
    titles = {sc.id: sc.title for sc in db.query(Scenario).all()}
    out: list[RecalledMemory] = []
    for memory in memories:
        # Resolved from (session, turn) rather than stored on the row: an edit or a re-roll
        # replaces a beat's text in place, and a stored event id could point at a line that
        # no longer says what the memory is about. The turn is the stable unit.
        source = db.scalars(
            select(Event)
            .where(Event.session_id == memory.session_id, Event.seq >= memory.turn_seq)
            .order_by(Event.seq)
            .limit(1)
        ).first()
        out.append(
            RecalledMemory(
                id=memory.id,
                characterId=memory.character_id,
                characterName=names.get(memory.character_id, "Someone"),
                gloss=memory.gloss,
                quote=memory.quote,
                quoteSpeakerName=names.get(memory.quote_speaker_id or ""),
                scenarioId=memory.scenario_id,
                scenarioTitle=titles.get(memory.scenario_id, "an earlier scene"),
                sessionId=memory.session_id,
                turnSeq=memory.turn_seq,
                eventId=source.id if source is not None else None,
                inThisSession=memory.session_id == session_id,
                contradictedBy=[
                    MemoryContradiction(
                        characterId=other.character_id,
                        characterName=names.get(other.character_id, "Someone"),
                        gloss=other.gloss,
                    )
                    for other in memory_store.contradictions(db, memory)
                ],
            )
        )
    return BeatMemoryResponse(eventId=event_id, memories=out)


@router.get(
    "/{scenario_id}/sessions/{session_id}/context", response_model=SceneKnowledgeResponse
)
def scene_context(scenario_id: str, session_id: str, db: Session = Depends(get_db)):
    """What the scene knows right now, in the player's terms.

    Assembled from the most recent turn's already-persisted trace rows, so it costs the turn
    path nothing and works on a **resumed** scene — which is exactly when a player most wants
    to ask what a long session still remembers.
    """
    crud.get_scenario(db, scenario_id)
    session = events_store.get_session(db, scenario_id, session_id)  # 404/400
    return scene_knowledge.scene_knowledge(db, session)


@router.post(
    "/{scenario_id}/sessions/{session_id}/recap", response_model=RecapResponse
)
def session_recap(
    scenario_id: str,
    session_id: str,
    body: RecapRequest,
    db: Session = Depends(get_db),
):
    """"Tell me what happened" — prose for the player, on demand.

    Runs the **same** agent compaction uses, so the recap a player reads cannot drift in tone
    or in what it considers a fact from the memory the cast reads. Never 500s on an
    unreachable model: an empty recap is a convenience not delivered, not a page that broke.
    """
    scenario = crud.get_scenario(db, scenario_id)
    session = events_store.get_session(db, scenario_id, session_id)  # 404/400
    through = body.through_seq
    if through is None:
        through = events_store.next_seq(db, session.id)
    return RecapResponse(
        text=history_compaction.recap(db, session, scenario, through_seq=through)
    )


@router.post(
    "/{scenario_id}/sessions/{session_id}/standing-direction",
    response_model=StandingDirectionResponse,
)
def clear_standing_direction(
    scenario_id: str,
    session_id: str,
    body: StandingDirectionRequest,
    db: Session = Depends(get_db),
):
    """Stop asking for some (or all) of what the scene still owes.

    A direction now outlives the turn it rode in on, which is the point — but a debt the
    player cannot cancel is a bug, not a feature. ``itemIds`` drops the named entries;
    ``None`` clears everything. Idempotent: ids that are already gone are simply not there.
    """
    crud.get_scenario(db, scenario_id)
    session = events_store.get_session(db, scenario_id, session_id)  # 404/400
    if body.item_ids is None:
        remaining: list[dict] = []
    else:
        drop = set(body.item_ids)
        rows = session.standing_direction if isinstance(session.standing_direction, list) else []
        remaining = [r for r in rows if isinstance(r, dict) and r.get("id") not in drop]
    direction_runtime.save_standing(db, session, remaining)
    db.commit()
    return StandingDirectionResponse(standing_direction=_standing(session))


@router.post("/{scenario_id}/sessions/{session_id}/close", response_model=SessionSummary)
def close_session(scenario_id: str, session_id: str, db: Session = Depends(get_db)):
    """Mark a play-through closed (the save-on-close signal). Idempotent; every turn is
    already persisted, so this only stamps ``closed_at`` / bumps recency."""
    crud.get_scenario(db, scenario_id)
    events_store.get_session(db, scenario_id, session_id)  # 404/400
    session = events_store.close_session(db, session_id)
    return _summary(db, session)


@router.get("/{scenario_id}/sessions/{session_id}/export")
def export_session(
    scenario_id: str,
    session_id: str,
    format: str = Query("json", pattern="^(json|md)$"),
    db: Session = Depends(get_db),
):
    """Download the full conversation record as JSON or Markdown (attachment).

    Server-generated from the persisted rows so it works identically for a live or a
    long-closed scene, and includes the graph/RAG diagnostics that only live in the trace.
    """
    scenario = crud.get_scenario(db, scenario_id)
    session = events_store.get_session(db, scenario_id, session_id)  # 404/400
    events = events_store.session_events(db, session_id)
    traces = events_store.session_traces(db, session_id)
    names = {c.id: c.name for c in crud.list_characters(db, scenario.storyline_id)}

    if format == "md":
        body = session_export.render_markdown(scenario, session, events, traces, names)
        media_type, ext = "text/markdown; charset=utf-8", "md"
    else:
        body = session_export.render_json(scenario, session, events, traces, names)
        media_type, ext = "application/json; charset=utf-8", "json"

    filename = f"mytheca-{scenario_id}-{session_id}.{ext}"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
