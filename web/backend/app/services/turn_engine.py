"""Turn engine — the runtime story loop.

Drives one player turn: persist the ``user_turn``, assemble Band-1 context, run the
per-character POV loop (one isolated LLM call per active speaker), and stream the
visible story events as NDJSON while persisting each.

Visible prose (``narration`` / ``character_dialogue``) **delta-streams**: the same
event (same id + seq) is emitted with incremental ``text`` + ``done: false`` until the
last chunk sets ``done: true`` (the client accumulates by id; the persisted row holds
the full text). ``character_action`` streams as one full event; ``internal_thought``
(``visibility: private_to_user``) streams to the player as a distinct "thinking" bubble
but is kept OUT of ``turn_beats`` — later speakers never condition on it. ``_Emitter``
centralizes the seq + persist + buffer + withhold-hidden plumbing every phase reuses.

Speaker selection is a **per-beat ReAct loop**: ``planner_agent.next_beat`` decides one
beat at a time (``speak`` / ``narrate`` / ``exit`` / ``end``) from the *present* roster,
with the POV character locked out. The loop is bounded by the scene's ``max_turns`` and a
runaway backstop of ``max(TURN_MAX_BEATS, 2 * len(cast) + 6)``. This replaced the earlier
one-shot director (``director_agent.who_is_up`` / ``rerank``), which is now dead code kept
only for its unit tests.

Over that loop sits the **scene direction** (Narrator-Guided Scenes): when the player is
directing — their own line in narrator mode, the separate ``guidance`` box under Player POV
— the turn owes a list of ``direction_agent`` requirements. The planner sees what is still
owed and how many beats are left; once the budget is as tight as the direction is long the
engine stops asking and runs ``direction_agent.schedule`` itself, so everything asked for
lands inside ``scenario.max_turns``. Each beat carries only *its* requirements into the
prompt, as an outcome to reach — the speaker still chooses their own words and stays in
character.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from typing import Any

from sqlalchemy.orm import Session

from app.agents import (
    character_turn_agent,
    direction_agent,
    director_agent,
    intent_agent,
    narrator_agent,
    planner_agent,
)
from app.agents._common import resolve_llm
from app.agents.direction_agent import DirectionRequirement, SceneDirection
from app.agents.reflection_agent import LlmConn
from app.core.config import get_settings
from app.core.errors import APIError
from app.core.ids import new_id
from app.events.envelope import StoryEvent
from app.events.stream import TurnTraceFrame, build_event, chunk_text
from app.memory import buffer
from app.models import Scenario
from app.schemas.base import EventType, Visibility
from app.schemas.play import TurnRequest
from app.services import (
    assembler,
    consistency,
    crud,
    emission,
    events_store,
    graph_reader,
    presence,
    reflection,
    relationships,
    stats,
    turn_writer,
    validator,
)
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
    ) -> "_LiveSegment":
        """Start streaming one event; the caller drives it with ``delta``/``close``."""
        return _LiveSegment(
            self,
            type_,
            character_id=character_id,
            visibility=visibility,
            buffer_role=buffer_role,
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


class _LiveSegment:
    """One event id being streamed live, so deltas can be emitted as text arrives.

    :meth:`_Emitter.emit_streamed` persists a finished string and replays it as fake
    deltas; this is the real thing — the row is written on :meth:`close`, once the text
    is actually complete, and every delta before that goes straight to the wire.
    """

    def __init__(
        self,
        emitter: "_Emitter",
        type_: EventType,
        *,
        character_id: str | None,
        visibility: Visibility | None,
        buffer_role: str | None,
    ) -> None:
        self._emitter = emitter
        self._type = type_
        self._character_id = character_id
        self._visibility = visibility
        self._buffer_role = buffer_role
        self._event_id = new_id("ev")
        self._seq = emitter.take_seq()
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
        self._emitter.persist(full, buffer_role=self._buffer_role, character_id=self._character_id)
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


class _Tracer:
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


def validate_turn_inputs(db: Session, scenario_id: str, req: TurnRequest) -> Scenario:
    """Pre-flight (before the 200 stream opens): scenario exists, text present, session valid."""
    scenario = crud.get_scenario(db, scenario_id)  # raises 404 when missing
    if not (req.text or "").strip():
        raise APIError(400, "bad_request", "Turn text is required.")
    if req.session_id:
        events_store.resolve_session(db, scenario_id, req.session_id)  # validates only
    return scenario


def run_turn(
    db: Session, scenario: Scenario, req: TurnRequest
) -> Iterator[StoryEvent | TurnTraceFrame]:
    """Run one turn, yielding the visible story events (and, when ``req.trace``, the
    interleaved diagnostic trace frames the Inspector renders) in order."""
    session = events_store.resolve_session(db, scenario.id, req.session_id)
    text = (req.text or "").strip()

    seq0 = events_store.next_seq(db, session.id)
    # The tracer persists every diagnostic step (keyed by this turn's opening seq) so the
    # scene's graph/RAG activity is reviewable later; it still only *streams* when opted in.
    tracer = _Tracer(
        req.trace, db=db, session_id=session.id, scenario_id=scenario.id, turn=seq0
    )

    # Assemble against committed history FIRST (read-only), so the Player POV member can be
    # resolved before anything is recorded, THEN push the player's line so it becomes
    # history for the next turn (the current line also seeds this turn's transcript, so it
    # is present even when the buffer is disabled).
    ctx = assembler.assemble_context(
        db,
        scenario,
        session.id,
        req.directed_at,
        player_text=text,
        tagged_doc_ids=req.tagged_doc_ids,
    )

    # Player POV: the player is speaking AS this character. Resolve it to a *present* cast
    # member (else fall back to the default guide/narrator behavior). When set, the player's
    # line IS the character's line — seeded/buffered as a `character` beat, persisted on the
    # user_turn row, and the character is locked out of the AI roster (below) so the model
    # never voices a second beat for them.
    pov = ctx.cast_by_id(req.pov_character_id) if req.pov_character_id else None
    if pov is not None and not pov.is_present:
        pov = None
    pov_id = pov.id if pov is not None else None

    events_store.record_user_turn(
        db,
        scenario_id=scenario.id,
        session_id=session.id,
        seq=seq0,
        text=text,
        directed_at=req.directed_at,
        pov=pov_id,
    )
    yield from tracer.emit(
        "turn",
        "You submitted a message",
        detail=text,
        data={"directedAt": req.directed_at, "mode": req.mode, "pov": pov_id},
    )

    # Push the player's line into the recent-turn buffer as history for next turn — as the
    # POV character's own line when POV is active (so later speakers react to "Mei said X"),
    # else as an ordinary player line.
    if pov is not None:
        buffer.push_turn(session.id, "character", text, character_id=pov.id)
    else:
        buffer.push_turn(session.id, "player", text)
    graph_available = bool(ctx.subgraph.get("available"))
    yield from tracer.emit(
        "assemble",
        f"Gathered the scene ({len(ctx.cast)} character(s) present)",
        detail=(
            "Loaded each character's stats + carried-over mood, the recent transcript, and"
            f" the story-graph subgraph ({'available' if graph_available else 'off/empty'})."
        ),
        data={
            "cast": [
                {"id": m.id, "name": m.name, "disposition": m.disposition} for m in ctx.cast
            ],
            "directedAt": req.directed_at,
            "graph": graph_available,
            "retrievedLore": bool(ctx.retrieved_lore),
        },
    )
    # RAG look-up (Band-1): the gate decides per turn whether to hit the vector store.
    fetched = ctx.gate_reason.startswith("fetch")
    yield from tracer.emit(
        "lore",
        "World-lore look-up (RAG)" + (" — matched" if fetched and ctx.retrieved_lore else ""),
        detail=(
            ("Fetched durable lore and folded it into the prompt." if ctx.retrieved_lore else "Ran a lookup but found nothing to add.")
            if fetched
            else "Skipped — nothing in your message needed a lore look-up this turn."
        ),
        data={"reason": ctx.gate_reason, "fetched": fetched, "injected": bool(ctx.retrieved_lore)},
    )
    # @-tagged context files: the player named these explicitly, so unlike the gated lore
    # above they always go in. Traced so the player can confirm the file actually landed —
    # the whole reason for tagging over relying on retrieval.
    if req.tagged_doc_ids:
        yield from tracer.emit(
            "files",
            "Tagged files"
            + (f" — {len(ctx.tagged_names)} attached" if ctx.tagged_names else " — none matched"),
            detail=(
                "Folded "
                + ", ".join(ctx.tagged_names)
                + " into the prompt as reference material (it grounds what is said; it does"
                " not steer the scene)."
                if ctx.tagged_names
                else "None of the tagged files could be read for this world."
            ),
            data={"names": ctx.tagged_names, "injected": bool(ctx.tagged_notes)},
        )

    emitter = _Emitter(db, scenario.id, session.id, start_seq=seq0 + 1)
    # The chronological this-turn transcript handed to each speaker so a later speaker
    # genuinely reacts to its predecessor (sequential by nature — §9). Under Player POV the
    # player's line seeds as the POV character's OWN beat (later speakers react to it as
    # "Mei said X"); the visible character event is intentionally WITHHELD — the client
    # already renders the player's line optimistically / on rehydrate, exactly as the plain
    # player line is today.
    if pov is not None:
        turn_beats: list[dict] = [{"role": "character", "text": text, "characterId": pov.id}]
    else:
        turn_beats = [{"role": "player", "text": text, "characterId": None}]

    # Durable consequences implied by the turn (populated from state_update events in
    # the branch/stat phase); routed off the hot path by the cold-path turn-writer.
    consequences: list[Consequence] = []

    # The continuity guard connection (resolved once; the LLM is already configured or
    # generation would have failed first). Also used by the puppet beats below.
    guard_conn = _resolve_conn(db) if len(ctx.cast) > 1 else None

    # Interpret the player's line: narrating, addressing someone, or DIRECTING a character
    # to act/speak (puppet)? This is what fixes attribution (Reactive Turn Director D1) —
    # a puppeted character performs the direction in its own voice; the addressed character
    # reacts, instead of a bystander answering the player's words.
    intent = intent_agent.interpret(db, ctx, text)
    # A UI-set target (e.g. a branch selection) addresses that character explicitly.
    if (
        req.directed_at
        and ctx.cast_by_id(req.directed_at) is not None
        and req.directed_at not in intent.addressed
        and req.directed_at not in intent.directed_actors
    ):
        intent.addressed.append(req.directed_at)
        if intent.kind == "freeform":
            intent.kind = "direct"
    yield from tracer.emit(
        "intent",
        f"Read your intent: {intent.kind}",
        detail=intent.directive,
        data={
            "kind": intent.kind,
            "actors": [m.name for cid in intent.directed_actors if (m := ctx.cast_by_id(cid))],
            "addressed": [m.name for cid in intent.addressed if (m := ctx.cast_by_id(cid))],
            "scope": intent.scope,
        },
    )

    # The scene direction (Narrator-Guided Scenes). Where it comes from depends on who the
    # player is speaking as:
    #  • POV mode — the ``text`` field is the CHARACTER'S line, so direction can only come
    #    from the separate guidance box; it is parsed on its own call.
    #  • Narrator mode — the player's line IS the direction, and the intent call above
    #    already broke it into requirements, so nothing extra is spent. An ordinary
    #    conversational line yields none, and the turn runs exactly as it did before.
    # Requirements naming an absent character (or the POV character, whom the AI never
    # voices) are rebound to the narrator so they can still be delivered.
    guidance = (req.guidance or "").strip()
    if guidance:
        direction = direction_agent.parse(db, ctx, guidance)
    elif pov is None and intent.requirements:
        direction = SceneDirection(text=intent.directive or text, requirements=intent.requirements)
    else:
        direction = SceneDirection()
    direction.rebind({m.id for m in ctx.cast if m.is_present}, locked_id=pov_id)
    if direction.active:
        yield from tracer.emit(
            "direction",
            f"You directed the scene ({len(direction.requirements)} thing(s) to deliver)",
            detail=direction.text,
            data={
                "source": "guidance" if guidance else "message",
                "requirements": [
                    {"text": r.text, "actor": _name_of(ctx, r.actor_id)}
                    for r in direction.requirements
                ],
            },
        )

    # Narration leads, before anyone speaks. Two cases (feedback #1/#2/#3):
    #  • Branch continuation — the player picked a narrative direction (``outcome``): open
    #    with a fuller "progression" paragraph that plays the choice out, then let the
    #    scene react below.
    #  • Cold scene open with NO direction — the narrator sets the moment and the turn is
    #    narrator-only (no character talks unprompted); the character loop is skipped.
    outcome = (req.outcome or "").strip()
    scene_opening = not ctx.recent_beats  # nothing committed before this turn
    narrated_open = False
    # Per-scene hard ceiling on the beats a single player message produces (Scene Dialogue
    # Updates). The planner may still end the turn earlier; this only caps a drawn-out
    # exchange. The ceiling counts EVERY emitted beat — character replies AND narrator beats
    # (request #3) — so a hard cap of N is never exceeded: the scene-setting narrated open
    # and any puppet performances count toward it, as does each mid-turn interstitial.
    # Resolved here (rather than beside the loop) because the opening narration below has to
    # know how much of the direction it must absorb.
    max_turns = max(1, scenario.max_turns)
    # A direction asking for more than the scene has beats cannot be spread one per beat, so
    # an opening narration absorbs EVERY narrator-owned line at once rather than letting some
    # fall off the end of the turn. With room to spare it takes just the first, and the rest
    # pace out across the loop.
    open_limit = None if max_turns <= len(direction.requirements) else 1
    if outcome:
        yield from tracer.emit(
            "plan", "The narrator plays out your choice", detail=outcome, data={"outcome": outcome}
        )
        owed = direction.for_actor(None)[:open_limit]
        narrated_open = yield from _narrator_interstitial(
            db, ctx, turn_beats, emitter,
            lead=_direction_lead(direction, owed, base=outcome), long=True,
        )
        if narrated_open:
            direction.satisfy(owed)
    elif scene_opening and not intent.directed_actors and not intent.addressed and intent.scope != "all":
        yield from tracer.emit(
            "plan",
            "The narrator opens the scene",
            detail="Scene start — the narrator sets the moment before anyone responds.",
        )
        owed = direction.for_actor(None)[:open_limit]
        narrated_open = yield from _narrator_interstitial(
            db, ctx, turn_beats, emitter,
            lead=_direction_lead(direction, owed, base="Open the scene."), long=True,
        )
        if narrated_open:
            direction.satisfy(owed)

    # Puppet beats first: each directed character performs the player's direction in its
    # OWN voice (not a reply to the player's words). The POV character is excluded — the
    # player already voiced them this turn, so the AI must not perform a second beat for them.
    puppet_members = [
        m
        for cid in intent.directed_actors
        if (m := ctx.cast_by_id(cid)) is not None and m.id != pov_id
    ]
    for speaker in puppet_members:
        yield from tracer.emit(
            "speaker",
            f"{speaker.name} performs your direction",
            detail=intent.directive,
            data={"characterId": speaker.id, "name": speaker.name, "puppet": True},
        )
        note = _relationship_note(
            ctx, speaker.id, intent.addressed or [m.id for m in ctx.cast if m.id != speaker.id]
        )
        if note:
            yield from tracer.emit("relationship", f"{speaker.name}'s ties", detail=note, data={"characterId": speaker.id})
        # A puppeted character performs the direction, so their own requirements ride on the
        # very beat the player asked for rather than waiting for a later one.
        owed = direction.for_actor(speaker.id)
        direction.satisfy(owed)
        yield from _generate_speaker(
            db, ctx, speaker, emitter, turn_beats, consequences,
            guard_conn=guard_conn, directive=intent.directive, relationship_note=note,
            direction=direction, requirements=owed, tracer=tracer,
        )

    # ReAct loop (D3): after each beat, re-decide the next one from the transcript so
    # far — which character acts (optionally addressing another), whether the narrator
    # sets context, or the turn ends. Unbounded by design — a whole-group direction walks
    # the entire cast (D2); TURN_MAX_BEATS is only a runaway backstop, and the ceiling
    # floors above the cast size so a large cast is never clipped.
    acted: list[str] = [m.id for m in puppet_members]
    # The POV character has already taken their beat (the player's line), so mark them acted:
    # a broadcast/crowd never re-selects them, and they still reflect at end-of-turn so their
    # interior stays current for when the AI takes them back over.
    if pov_id is not None:
        acted.append(pov_id)
    max_beats = max(get_settings().turn_max_beats, 2 * len(ctx.cast) + 6)
    scene_beats = len(puppet_members) + (1 if narrated_open else 0)
    needs_branch = False
    beats = 0
    while beats < max_beats:
        # Presence can change mid-turn (an exit beat, a vital stat bottoming out), so re-own
        # any requirement whose character just left before scheduling against it.
        direction.rebind({m.id for m in ctx.cast if m.is_present}, locked_id=pov_id)
        outstanding = direction.outstanding()
        remaining = max_turns - scene_beats
        if scene_beats >= max_turns:
            yield from tracer.emit(
                "plan",
                "Reached the scene's turn limit",
                detail=(
                    f"Stopped after {scene_beats} beat(s) (scene cap of {max_turns})."
                    + (
                        f" {len(outstanding)} part(s) of your direction did not fit —"
                        " raise the scene's turn limit to give it more room."
                        if outstanding
                        else ""
                    )
                ),
                data={"end": True, "undelivered": [r.text for r in outstanding]},
            )
            break
        # The direction is a contract, and the scene cap is hard — so once what is still owed
        # would fill every beat that is left, the planner's judgement can no longer be
        # afforded and the engine schedules the rest itself. Below that line the planner
        # decides freely, with the outstanding list and the budget in its prompt.
        decision: planner_agent.BeatDecision | None = None
        forced_reason = "the rest of your direction has to fit the beats that are left"
        if not outstanding or len(outstanding) < remaining:
            decision = planner_agent.next_beat(
                db, ctx, intent, turn_beats, acted,
                scene_opening=scene_opening and not narrated_open, locked_id=pov_id,
                direction=direction if direction.active else None, remaining_beats=remaining,
            )
            # An "end" while the player is still owed something is not the planner's call.
            if decision.action == "end" and outstanding:
                decision = None
                forced_reason = "your direction is not delivered yet"
        if decision is None:
            scheduled = direction_agent.schedule(outstanding, remaining)
            if scheduled is None:
                break
            direction.satisfy(scheduled.requirements)
            owed = scheduled.requirements
            forced_actor = ctx.cast_by_id(scheduled.actor_id) if scheduled.actor_id else None
            if forced_actor is None:
                yield from tracer.emit(
                    "direction",
                    "The narrator delivers your direction",
                    detail=forced_reason,
                    data={"requirements": [r.text for r in owed]},
                )
                yield from _narrator_interstitial(
                    db, ctx, turn_beats, emitter,
                    lead=_direction_lead(direction, owed),
                    # Several requirements bundled into one closing beat need a paragraph,
                    # not a two-sentence transition, to actually land them all.
                    long=len(owed) > 1,
                )
            else:
                yield from tracer.emit(
                    "direction",
                    f"{forced_actor.name} delivers your direction",
                    detail=forced_reason,
                    data={"characterId": forced_actor.id, "requirements": [r.text for r in owed]},
                )
                note = _relationship_note(
                    ctx, forced_actor.id, [m.id for m in ctx.cast if m.id != forced_actor.id]
                )
                yield from _generate_speaker(
                    db, ctx, forced_actor, emitter, turn_beats, consequences,
                    guard_conn=guard_conn, relationship_note=note,
                    direction=direction, requirements=owed, tracer=tracer,
                )
                acted.append(forced_actor.id)
            beats += 1
            scene_beats += 1
            continue
        # Defensive backstop (decision #1): the POV character is the player's to voice, never
        # the AI's. The planner already excludes them from the roster, but if a stray reply
        # ever names them, treat it as the turn ending rather than voicing a duplicate beat.
        if pov_id is not None and decision.action == "speak" and decision.actor_id == pov_id:
            yield from tracer.emit(
                "plan",
                "The turn ends",
                detail="The POV character is voiced by the player.",
                data={"end": True},
            )
            break
        if decision.action == "end":
            # Every step that stops the beat loop carries ``data.end = True`` — the
            # structured signal the story player's turn-status strip reads to say "the turn
            # is ending". The titles are prose and will drift; the flag will not.
            needs_branch = decision.needs_branch
            yield from tracer.emit(
                "plan",
                "The turn ends",
                detail=decision.reason or "The direction is satisfied.",
                data={"end": True},
            )
            break
        if decision.action == "narrate":
            yield from tracer.emit("plan", "The narrator sets the scene", detail=decision.reason)
            # One narrator-owned requirement per narrated beat, so a multi-part direction
            # paces out across the turn instead of arriving as a single summary paragraph.
            owed = direction.for_actor(None)[:1]
            direction.satisfy(owed)
            yield from _narrator_interstitial(
                db, ctx, turn_beats, emitter,
                lead=_direction_lead(direction, owed) or None,
            )
            beats += 1
            scene_beats += 1
            continue
        if decision.action == "exit":
            # The director removes a character the story already wrote out (dead/left/…).
            # Marks them non-present so no later beat picks them; a structural op that costs
            # a runaway-backstop beat but not the player's scene-turn budget.
            leaver = ctx.cast_by_id(decision.actor_id) if decision.actor_id else None
            if leaver is None or decision.status is None:
                break
            yield from tracer.emit(
                "plan",
                f"{leaver.name} exits the scene ({decision.status})",
                detail=decision.reason,
                data={"characterId": leaver.id, "status": decision.status},
            )
            yield from _apply_presence_change(
                emitter, leaver, decision.status, decision.reason, auto=True, tracer=tracer
            )
            beats += 1
            continue
        actor = ctx.cast_by_id(decision.actor_id) if decision.actor_id else None
        if actor is None:
            break
        addressing = ctx.cast_by_id(decision.addressing_id) if decision.addressing_id else None
        yield from tracer.emit(
            "plan",
            f"{actor.name} is up next" + (f" (to {addressing.name})" if addressing else ""),
            detail=decision.reason,
            data={
                "actor": actor.name,
                "addressing": addressing.name if addressing else None,
                "register": decision.register,
                "stakes": decision.stakes or None,
            },
        )
        yield from tracer.emit(
            "speaker", f"{actor.name} responds", data={"characterId": actor.id, "name": actor.name}
        )
        note = _relationship_note(
            ctx,
            actor.id,
            [addressing.id] if addressing else [m.id for m in ctx.cast if m.id != actor.id],
        )
        if note:
            yield from tracer.emit("relationship", f"{actor.name}'s ties", detail=note, data={"characterId": actor.id})
        # One of this actor's own requirements rides on the beat the planner chose for them
        # (the rest, if any, wait for a later beat or the forced schedule above).
        owed = direction.for_actor(actor.id)[:1]
        direction.satisfy(owed)
        yield from _generate_speaker(
            db, ctx, actor, emitter, turn_beats, consequences,
            guard_conn=guard_conn, relationship_note=note,
            register=decision.register, stakes=decision.stakes,
            direction=direction, requirements=owed, tracer=tracer,
        )
        acted.append(actor.id)
        beats += 1
        scene_beats += 1
    if beats >= max_beats:  # loop exhausted without an explicit end (runaway backstop)
        yield from tracer.emit(
            "plan",
            "Reached the turn's beat limit",
            detail=f"Stopped after {beats} beats (runaway backstop).",
            data={"end": True},
        )
    if direction.active:
        undelivered = direction.outstanding()
        yield from tracer.emit(
            "direction",
            (
                "Your direction was delivered in full"
                if not undelivered
                else f"{len(undelivered)} part(s) of your direction went undelivered"
            ),
            detail=" · ".join(direction.summary()),
            data={
                "delivered": len(direction.requirements) - len(undelivered),
                "total": len(direction.requirements),
                "undelivered": [r.text for r in undelivered],
            },
        )

    # Nobody produced anything at all (no narration, no character) → a quiet holding
    # narration. A narrator-only open / branch progression already spoke, so skip it then.
    if not acted and not narrated_open:
        yield from emitter.emit(
            "narration", {"text": "The scene waits, quiet.", "done": True}, buffer_role="narrator"
        )

    # Follow-up suggestions: offer up to ``scenario.suggestions_count`` (0 disables) direct
    # follow-ups to the most recent line at the end of every turn — count-driven, no longer
    # gated on the planner's rarely-set ``needsBranch`` flag (which left the feature dead).
    # ``needs_branch`` now only colors the trace copy. Stats inform which options surface,
    # but never gate the choice mechanically (no dice — D11).
    branches: list[dict] = []
    suggestions_count = max(0, min(scenario.suggestions_count, 4))
    if suggestions_count > 0:
        # Under Player POV, the follow-ups must read like something the POV character would
        # say next (they flow into the composer as the player's own next line), so use the
        # in-voice POV path; otherwise the situation-wide branch path. Both emit via
        # branch_choices, so the client's choose→composer flow is unchanged.
        if pov is not None:
            branches = director_agent.propose_pov_lines(
                db, ctx, turn_beats, pov, count=suggestions_count
            )
        else:
            branches = director_agent.propose_branches(db, ctx, turn_beats, count=suggestions_count)
        if branches:
            yield from emitter.emit("branch_choices", {"choices": branches})
            yield from tracer.emit(
                "branch",
                f"Offered {len(branches)} follow-up suggestion(s)",
                detail=(
                    "A fork — pick one to steer where the scene goes next."
                    if needs_branch
                    else "Follow-ups to the latest line — pick one to steer where the scene goes next."
                ),
                data={"choices": [b.get("label", "") for b in branches]},
            )

    # Cold path (Band 3): runs after the last event is yielded — never blocks the
    # player, best-effort, no-op when there are no consequences or the graph is down.
    cons_summaries = [c.summary for c in consequences if c.summary]
    yield from tracer.emit(
        "commit",
        (
            f"Committing {len(consequences)} change(s) to the story graph"
            if consequences
            else "Nothing durable to commit to the story graph"
        ),
        detail=(
            "Written to the story graph (Neo4j) after the turn: " + " · ".join(cons_summaries)
            if cons_summaries
            else "This turn moved no stat/relationship, so the knowledge graph is unchanged."
        ),
        data={"consequences": len(consequences), "changes": cons_summaries},
    )
    turn_writer.write_turn(
        db,
        scenario=scenario,
        session_id=session.id,
        turn_seq=seq0,
        summary=_turn_summary(turn_beats),
        consequences=consequences,
    )

    # Read-time reflection interlude (Band 4 / §P9): characters reflect while the player
    # reads, writing the interior state Band-1 reads back next turn. Best-effort and off
    # the hot path (branch-keyed when a fork was offered so a character pre-leans into
    # whichever path the player takes). In a crowded scene (N>2) reflection is
    # **universal** — the silent watchers also update their interior from the beat (§P10);
    # a two-hander only reflects who actually spoke. Dispatched off the request thread
    # when TURN_ASYNC_FINALIZE is on (P11) so the stream closes without waiting on the N
    # reflection LLM calls; inline (deterministic) otherwise.
    spoke = [m for cid in dict.fromkeys(acted) if (m := ctx.cast_by_id(cid)) is not None]
    # A crowd reflects universally, but only the characters still PRESENT — a dead/departed
    # one won't re-enter the scene, so there's no interior state to carry forward.
    present_cast = [m for m in ctx.cast if m.is_present]
    reflection_targets = present_cast if len(present_cast) > 2 else spoke
    reflection.dispatch_reflection(db, ctx, reflection_targets, turn_beats, branches=branches, seq=seq0)

    # First turn of a new session (D4 / P3): seed initial character↔character relationships
    # from the authored bios into the story graph (best-effort, idempotent, off the hot
    # path — a graph/LLM outage is a clean no-op). The cold path evolves them thereafter.
    if req.session_id is None:
        seeded = relationships.ensure_seeded(db, scenario)
        yield from tracer.emit(
            "relationships",
            f"Seeded {len(seeded)} relationship(s) from bios" if seeded else "Relationships not seeded",
            detail=(
                "Initial character-to-character edges from the cast's backgrounds: "
                + " · ".join(seeded)
                if seeded
                else "Already seeded, the graph is off, or the bios implied none."
            ),
            data={"seeded": len(seeded), "edges": seeded},
        )
    yield from tracer.emit(
        "reflection",
        f"{len(reflection_targets)} character(s) reflect",
        detail=(
            "Each privately updates its stance for next turn"
            + (" (branch-keyed for the fork above)" if branches else "")
            + ("; the whole cast reflects in a crowd" if len(present_cast) > 2 else "")
            + "."
        ),
        data={"targets": [m.name for m in reflection_targets], "universal": len(present_cast) > 2},
    )

    # Mark the session freshly played so resume can pick the most recent play-through.
    events_store.touch_session(db, session.id)


def _turn_summary(turn_beats: list[dict]) -> str:
    """A one-line summary of the turn for the appended :Event node."""
    parts = [str(b.get("text", "")).strip() for b in turn_beats if b.get("text")]
    return " · ".join(parts)[:240]


def _narrator_interstitial(
    db: Session,
    ctx: TurnContext,
    turn_beats: list[dict],
    emitter: _Emitter,
    *,
    lead: str | None = None,
    long: bool = False,
) -> Generator[StoryEvent, None, bool]:
    """Emit an optional narrator beat; skip silently on failure. Returns whether a beat
    was actually emitted (so the caller can tell a real opening from a no-op).

    ``lead``/``long`` drive the fuller opening + branch-progression passage (feedback
    #1/#2/#3); the default (both unset) is the short between-speakers transition beat.

    The prose streams as the model writes it. A scene's first message is narrator-led, so
    this is the very first thing a new player sees — it is the beat that most needs to
    start arriving early rather than landing whole after a long silence."""
    stream = narrator_agent.stream_interstitial(db, ctx, turn_beats, lead=lead, long=long)
    live = emitter.open_stream("narration", buffer_role="narrator")
    try:
        while True:
            delta = next(stream)
            if delta.answer:
                yield from live.delta(delta.answer)
    except StopIteration as stop:
        text = stop.value
    if not text:
        # Nothing usable — discard the event id rather than persisting an empty beat.
        return False
    yield from live.close()
    turn_beats.append({"role": "narrator", "text": live.text, "characterId": None})
    return True


def _name_of(ctx: TurnContext, character_id: str | None) -> str | None:
    """The cast member's display name for a trace payload (``None`` → the narrator)."""
    member = ctx.cast_by_id(character_id) if character_id else None
    return member.name if member is not None else None


def _direction_lead(
    direction: SceneDirection, requirements: list[DirectionRequirement], *, base: str = ""
) -> str:
    """Compose the narrator's ``lead`` from the player's direction.

    The whole direction gives the beat its destination; ``requirements`` are the specific
    parts THIS beat owes. Returns ``""`` when there is nothing to steer by, which callers
    turn back into ``None`` so the narrator keeps its plain transition prompt.
    """
    parts = [base] if base else []
    if direction.text.strip():
        parts.append(f"The player is directing this scene: {direction.text.strip()}")
    if requirements:
        parts.append(
            "This beat has to make the following actually happen: "
            + "; ".join(r.text for r in requirements)
            + ". Narrate it as events in the scene — do not restate the direction."
        )
    return " ".join(parts)


def _resolve_conn(db: Session) -> LlmConn | None:
    """Resolve the LLM connection for the mid-turn guards; ``None`` when unconfigured."""
    try:
        return resolve_llm(db)
    except APIError:
        return None


def _has_prior_character_beat(turn_beats: list[dict]) -> bool:
    """True once a character has already spoken this turn (the guard's precondition)."""
    return any(b.get("role") == "character" for b in turn_beats)


def _relationship_note(ctx: TurnContext, speaker_id: str, other_ids: list[str]) -> str:
    """A plain-language summary of how ``speaker`` relates to the others (graph, 2-hop).

    Best-effort → "" when the graph is off / empty (Reactive Turn Director D4)."""
    ctxrel = graph_reader.relationship_context(speaker_id, other_ids)
    lines: list[str] = []
    for d in ctxrel.get("direct", []):
        verb = str(d.get("type", "")).replace("_", " ")
        reason = f" ({d['reason']})" if d.get("reason") else ""
        if d.get("outgoing"):
            lines.append(f"You {verb} {d['name']}{reason}.")
        else:
            lines.append(f"{d['name']} {verb} you{reason}.")
    seen: set[tuple[str, str]] = set()
    for i in ctxrel.get("indirect", []):
        key = (str(i.get("name")), str(i.get("via")))
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"You and {i['name']} are both connected to {i['via']}.")
    return " ".join(lines[:8])


def _prior_transcript(ctx: TurnContext, turn_beats: list[dict]) -> str:
    """Render the beats established so far THIS turn (the continuity guard's context)."""
    names = {m.id: m.name for m in ctx.cast}
    lines: list[str] = []
    for beat in turn_beats:
        text = str(beat.get("text", "")).strip()
        if not text:
            continue
        role = beat.get("role")
        if role == "player":
            who = "Player"
        elif role == "narrator":
            who = "Narrator"
        else:
            cid = beat.get("characterId")
            who = names.get(cid, "Someone") if cid else "Someone"
        lines.append(f"{who}: {text}")
    return "\n".join(lines)


def _stream_emission(
    db: Session,
    ctx: TurnContext,
    speaker: CastMember,
    emitter: _Emitter,
    turn_beats: list[dict],
    consequences: list[Consequence],
    *,
    roster: dict[int, str],
    directive: str | None,
    relationship_note: str | None,
    register: str | None,
    stakes: str,
    scene_direction: str,
    owed: list[str],
    tracer: _Tracer,
    live: bool,
) -> Generator[StoryEvent | TurnTraceFrame, None, tuple[str, int | None, int]]:
    """Drive one character generation as a stream; return ``(raw, prompt_tokens, impact)``.

    When ``live``, each segment is emitted, appended to ``turn_beats`` and traced the
    moment the parser recognises it — so the character's private thought completes while
    their spoken line is still being written, which is the whole point of the exercise.
    When not (a beat the continuity guard will judge), nothing is emitted here and the
    caller runs the ordinary post-verdict path; the raw emission is identical either way.

    ``impact`` (Σ|stat delta|) is only meaningful on the live path — the guarded path
    computes its own from the post-verdict segments.
    """
    stream = character_turn_agent.stream_line(
        db, ctx, speaker, turn_beats=turn_beats, directive=directive,
        relationship_note=relationship_note, register=register, stakes=stakes,
        scene_direction=scene_direction, requirements=owed,
    )
    acc = emission.EmissionAccumulator(roster=roster, fallback_speaker_id=speaker.id)
    open_segments: dict[int, _LiveSegment] = {}
    buffered: dict[int, str] = {}
    impact = 0

    try:
        while True:
            delta = next(stream)
            if not live or not delta.answer:
                # Still feed the parser so the raw emission and segment list are the same
                # on both paths — only the emitting is conditional.
                if delta.answer:
                    acc.push(delta.answer)
                continue
            for seg in acc.push(delta.answer):
                impact += yield from _emit_segment_delta(
                    db, ctx, speaker, emitter, turn_beats, consequences,
                    seg, open_segments, buffered, tracer,
                )
    except StopIteration as stop:
        raw, prompt_tokens = stop.value

    if live:
        for seg in acc.finish():
            impact += yield from _emit_segment_delta(
                db, ctx, speaker, emitter, turn_beats, consequences,
                seg, open_segments, buffered, tracer,
            )
        # A stream that ended mid-segment (a truncated completion) must not leave an
        # event open and unpersisted.
        for live_seg in open_segments.values():
            yield from live_seg.close()
        open_segments.clear()
    return raw, prompt_tokens, impact


def _emit_segment_delta(
    db: Session,
    ctx: TurnContext,
    speaker: CastMember,
    emitter: _Emitter,
    turn_beats: list[dict],
    consequences: list[Consequence],
    seg: emission.SegmentDelta,
    open_segments: dict[int, _LiveSegment],
    buffered: dict[int, str],
    tracer: _Tracer,
) -> Generator[StoryEvent | TurnTraceFrame, None, int]:
    """Route one parsed increment to the wire; return the stat impact it carried.

    Prose that reads well arriving piecemeal (``internal_thought``, ``character_dialogue``)
    delta-streams. ``character_action`` is held and sent whole: it is one short beat, and
    the client folds it into the speaker's open bubble — a rule that only works while the
    bubble has no spoken text yet. The JSON types are held because half an object is not
    parseable, and are applied through the same handlers the batch path uses.
    """
    if seg.type in ("internal_thought", "character_dialogue"):
        live_seg = open_segments.get(seg.index)
        if live_seg is None:
            live_seg = emitter.open_stream(
                seg.type,
                character_id=seg.character_id,
                visibility="private_to_user" if seg.type == "internal_thought" else None,
                buffer_role=None if seg.type == "internal_thought" else "character",
            )
            open_segments[seg.index] = live_seg
        if seg.text:
            yield from live_seg.delta(seg.text)
        if seg.done:
            text = live_seg.text
            yield from live_seg.close()
            open_segments.pop(seg.index, None)
            if seg.type == "internal_thought":
                # Kept OUT of turn_beats: it is the character's interiority, not shared
                # dialogue, and later speakers must never condition on it.
                yield from tracer.emit(
                    "thinking", f"{speaker.name} thinks (private)",
                    detail=text, data={"characterId": seg.character_id},
                )
            else:
                turn_beats.append(
                    {"role": "character", "text": text, "characterId": seg.character_id}
                )
                yield from tracer.emit(
                    "dialogue", f"{speaker.name} speaks",
                    detail=text, data={"characterId": seg.character_id},
                )
        return 0

    # Held types: accumulate, act on close.
    buffered[seg.index] = buffered.get(seg.index, "") + seg.text
    if not seg.done:
        return 0
    body = buffered.pop(seg.index, "")
    if not body:
        return 0
    if seg.type == "character_action":
        yield from emitter.emit(
            "character_action",
            {"characterId": seg.character_id, "text": body},
            buffer_role="character",
            character_id=seg.character_id,
        )
        turn_beats.append({"role": "character", "text": body, "characterId": seg.character_id})
        yield from tracer.emit(
            "action", f"{speaker.name} acts", detail=body, data={"characterId": seg.character_id}
        )
        return 0
    if seg.type == "state_update":
        return (
            yield from _apply_stat_change(
                db, ctx, seg.character_id, body, emitter, consequences, tracer=tracer
            )
        )
    if seg.type == "relationship_update":
        yield from _apply_relationship_change(ctx, seg.character_id, body, consequences, tracer)
        return 0
    if seg.type == "presence_change":
        yield from _apply_declared_presence(ctx, seg.character_id, body, emitter, tracer)
    return 0


def _generate_speaker(
    db: Session,
    ctx: TurnContext,
    speaker: CastMember,
    emitter: _Emitter,
    turn_beats: list[dict],
    consequences: list[Consequence],
    *,
    guard_conn: LlmConn | None = None,
    directive: str | None = None,
    relationship_note: str | None = None,
    register: str | None = None,
    stakes: str = "",
    direction: SceneDirection | None = None,
    requirements: list[DirectionRequirement] | None = None,
    tracer: _Tracer | None = None,
) -> Generator[StoryEvent | TurnTraceFrame, None, int]:
    """Generate one speaker's beat, guard it for continuity, emit its events, append them
    to ``turn_beats``, and return the beat's impact (Σ|stat delta|) for the live queue.

    ``register``/``stakes`` are the planner's read of this beat's moment (see
    ``planner_agent.BeatDecision``); they reach the character prompt's recency tail so the
    speaker performs against a stated situation instead of inferring one. A puppet beat runs
    before the planner has decided anything — and a forced direction beat runs *instead* of
    asking it — so both carry no register and the prompt falls back to its generic "read the
    moment" cue.

    ``directive`` marks a **puppet** beat (the player directed this character): the
    character performs it in-voice and the continuity guard is skipped (there is nothing
    to contradict — the player asked for it). ``relationship_note`` folds the speaker's
    graph relationships (to whom they address, + 2-hop) into the prompt (D4).

    ``direction`` is where the player is steering the whole scene (context every speaker
    plays toward) and ``requirements`` are the parts THIS beat owes — outcomes the character
    reaches in their own words, never lines to recite (Narrator-Guided Scenes)."""
    tr = tracer or _Tracer(False)
    roster = {i + 1: m.id for i, m in enumerate(ctx.cast)}
    scene_direction = direction.text.strip() if direction is not None else ""
    owed = [r.text for r in requirements or []]
    # The continuity guard inspects a COMPLETE candidate line and can reject it, so a beat
    # it will judge cannot also be shown as it arrives — a rejected line would have to
    # un-write itself on screen. It only runs once someone has already spoken this turn,
    # which splits the work cleanly: the turn's first beat (the longest wait, and the one
    # the player is actually staring at) streams its prose live, while a later beat holds
    # its prose for the verdict. Both stream the model's REASONING either way, so every
    # beat shows something happening rather than nothing.
    guarded = guard_conn is not None and not directive and _has_prior_character_beat(turn_beats)
    raw, prompt_tokens, streamed_impact = yield from _stream_emission(
        db, ctx, speaker, emitter, turn_beats, consequences,
        roster=roster, directive=directive, relationship_note=relationship_note,
        register=register, stakes=stakes, scene_direction=scene_direction, owed=owed,
        tracer=tr, live=not guarded,
    )
    segments = emission.parse_emission(raw, roster=roster, fallback_speaker_id=speaker.id)

    # Consistency guard (§P10): once a character has already spoken this turn, a later
    # line must not contradict the established beats. Regenerate once with the reason if
    # it does; best-effort (an unconfigured/failed guard leaves the line as-is).
    if guarded:
        assert guard_conn is not None
        candidate = " ".join(
            s.text for s in segments if s.type in ("character_action", "character_dialogue")
        )
        verdict = consistency.review(
            guard_conn,
            stable_prefix=ctx.stable_prefix,
            prior=_prior_transcript(ctx, turn_beats),
            candidate=candidate,
        )
        yield from tr.emit(
            "consistency",
            "Continuity check",
            detail=("passed" if verdict.consistent else f"contradiction — regenerating: {verdict.reason}"),
            data={"characterId": speaker.id, "consistent": verdict.consistent},
        )
        if not verdict.consistent:
            raw, prompt_tokens = character_turn_agent.generate_line_with_usage(
                db, ctx, speaker, turn_beats=turn_beats, correction=verdict.reason,
                relationship_note=relationship_note, register=register, stakes=stakes,
                scene_direction=scene_direction, requirements=owed,
            )
            segments = emission.parse_emission(raw, roster=roster, fallback_speaker_id=speaker.id)

    # Exact context-window usage: the server-reported input-token count for this
    # character call — the real size of everything actually sent (output contract +
    # World Primer + stat guidance + transcript). Streamed live and persisted (the
    # tracer writes it regardless of the opt-in) so the story player's context dial
    # reads the truth, not a char/4 estimate. Omitted when the endpoint reports no
    # usage (the dial then keeps its heuristic fallback).
    if prompt_tokens is not None:
        yield from tr.emit(
            "context",
            "Context window",
            detail=f"{prompt_tokens:,} tokens sent to the model",
            data={"characterId": speaker.id, "promptTokens": prompt_tokens},
        )

    if not guarded:
        # The live path already emitted, appended and traced every segment as it arrived.
        return streamed_impact

    impact = 0
    for seg in segments:
        if seg.type == "internal_thought":
            # The character's private thought: streamed to the PLAYER as its own "thinking"
            # bubble (visibility private_to_user), and surfaced in the Inspector trace — but
            # kept OUT of ``turn_beats`` so later speakers never condition on it (it is the
            # character's interiority, not shared dialogue).
            yield from emitter.emit(
                "internal_thought",
                {"characterId": seg.character_id, "text": seg.text},
                visibility="private_to_user",
            )
            yield from tr.emit(
                "thinking",
                f"{speaker.name} thinks (private)",
                detail=seg.text,
                data={"characterId": seg.character_id},
            )
        elif seg.type == "character_action":
            yield from emitter.emit(
                "character_action",
                {"characterId": seg.character_id, "text": seg.text},
                buffer_role="character",
                character_id=seg.character_id,
            )
            turn_beats.append({"role": "character", "text": seg.text, "characterId": seg.character_id})
            yield from tr.emit(
                "action", f"{speaker.name} acts", detail=seg.text, data={"characterId": seg.character_id}
            )
        elif seg.type == "character_dialogue":
            yield from emitter.emit_streamed(
                "character_dialogue",
                seg.text,
                character_id=seg.character_id,
                buffer_role="character",
            )
            turn_beats.append({"role": "character", "text": seg.text, "characterId": seg.character_id})
            yield from tr.emit(
                "dialogue", f"{speaker.name} speaks", detail=seg.text, data={"characterId": seg.character_id}
            )
        elif seg.type == "state_update":
            impact += yield from _apply_stat_change(
                db, ctx, seg.character_id, seg.text, emitter, consequences, tracer=tr
            )
        elif seg.type == "relationship_update":
            yield from _apply_relationship_change(ctx, seg.character_id, seg.text, consequences, tr)
        elif seg.type == "presence_change":
            yield from _apply_declared_presence(ctx, seg.character_id, seg.text, emitter, tr)
    return impact


def _apply_declared_presence(
    ctx: TurnContext,
    character_id: str,
    raw: str,
    emitter: _Emitter,
    tracer: _Tracer,
) -> Generator[StoryEvent | TurnTraceFrame, None, None]:
    """Apply a character's self-declared ``<type:presence_change>`` (leaving/collapsing).

    Validated against the declarer's current status (an illegal/no-op change is dropped);
    a valid one removes them from the selectable pool for the rest of the turn."""
    member = ctx.cast_by_id(character_id)
    if member is None:
        return
    result = validator.validate_presence(raw, current=member.presence)
    if result is None:
        yield from tracer.emit(
            "presence",
            "Proposed presence change dropped",
            detail="Illegal or no-op transition — ignored.",
            data={"characterId": character_id},
        )
        return
    status, reason = result
    yield from _apply_presence_change(emitter, member, status, reason, auto=True, tracer=tracer)


# Plain-language trace copy per presence transition (falls back to the free-text reason).
_PRESENCE_DETAIL = {
    "unconscious": "Knocked out — present but can't act until revived.",
    "departed": "No longer an active participant (body remains).",
    "left": "Walked out of the scene.",
    "dead": "Removed from the scene — permanently.",
    "present": "Back in the scene.",
}


def _apply_presence_change(
    emitter: _Emitter,
    member: CastMember,
    status: str,
    reason: str,
    *,
    auto: bool,
    tracer: _Tracer,
) -> Generator[StoryEvent | TurnTraceFrame, None, None]:
    """Emit a ``character_status_change`` and mutate the in-memory cast member's presence.

    Mutating ``member.presence`` in place is what makes the removal take effect *this* turn:
    the planner reads ``ctx.cast`` each beat, so a non-``present`` member drops off the
    selectable roster immediately. ``auto`` marks an engine-detected change (stat trigger,
    planner ``exit``, or self-declaration) so the client can offer an undo; a manual player
    override sets it false. Emits no ``turn_beats`` entry — presence surfaces in the cast
    rail, not the transcript (the triggering narration/line already told the story)."""
    member.presence = status
    yield from emitter.emit(
        "character_status_change",
        {"characterId": member.id, "status": status, "reason": reason, "auto": auto},
    )
    yield from tracer.emit(
        "presence",
        f"{member.name} → {status}",
        detail=reason or _PRESENCE_DETAIL.get(status, ""),
        data={"characterId": member.id, "status": status, "auto": auto},
    )


def _apply_relationship_change(
    ctx: TurnContext,
    source_id: str,
    raw: str,
    consequences: list[Consequence],
    tracer: _Tracer,
) -> Iterator[TurnTraceFrame]:
    """Validate a proposed relationship change and record it as a relational Consequence.

    A valid change becomes a ``Consequence`` carrying ``target_id`` + ``edge_type``, which
    the cold-path turn-writer reifies as the directed graph edge (evolve in play — D4/P5).
    Unknown/malformed → dropped. Emits no story event (relationships surface via the
    graph, not the transcript)."""
    names = {m.id: m.name for m in ctx.cast}
    src_name = names.get(source_id, "Someone")
    patch = validator.validate_relationship(
        source_id, raw, cast=[(m.id, m.name) for m in ctx.cast]
    )
    if patch is None:
        yield from tracer.emit(
            "relationship_change",
            "Proposed relationship dropped",
            detail="Unknown target or type — ignored.",
        )
        return
    tgt_name = names.get(patch.target_id, patch.target_id)
    consequences.append(
        Consequence(
            id=new_id("cons"),
            summary=f"{src_name} {patch.type} {tgt_name}: {patch.reason}".strip(),
            source_id=patch.source_id,
            reason=patch.reason,
            target_id=patch.target_id,
            edge_type=patch.type,
            weight=1.0,
            origin={"kind": "relationship"},
        )
    )
    yield from tracer.emit(
        "relationship_change",
        f"{src_name} now {patch.type.replace('_', ' ')} {tgt_name}",
        detail=patch.reason,
        data={"source": src_name, "type": patch.type, "target": tgt_name},
    )


def _apply_stat_change(
    db: Session,
    ctx: TurnContext,
    character_id: str,
    raw: str,
    emitter: _Emitter,
    consequences: list[Consequence],
    *,
    tracer: _Tracer | None = None,
) -> Generator[StoryEvent | TurnTraceFrame, None, int]:
    """Validate + clamp a proposed stat change, apply it (hot path), emit, and record it.

    Returns the change's impact (``|delta|``, ``0`` when dropped) so the live queue can
    scale its re-rank + cascade to how much the beat actually moved.
    """
    tr = tracer or _Tracer(False)
    patch = validator.validate_stat(db, ctx.storyline_id, character_id, raw)
    if patch is None:  # unknown stat / malformed → dropped
        yield from tr.emit(
            "stat",
            "Proposed stat change dropped",
            detail="The character proposed an unknown or malformed stat — ignored.",
            data={"characterId": character_id},
        )
        return 0
    # Apply on the hot path (clamped again — idempotent); then emit the full event.
    value = patch.value if patch.value is not None else 0
    stats.set_character_stats(db, patch.character_id, {patch.key: value})
    yield from emitter.emit(
        "state_update", {"patch": {}, "stat": patch.model_dump(by_alias=True)}
    )
    delta = patch.delta or 0
    yield from tr.emit(
        "stat",
        f"{patch.key} {delta:+d} → {value}",
        detail=patch.reason,
        data={"characterId": patch.character_id, "key": patch.key, "delta": delta, "value": value},
    )
    consequences.append(
        Consequence(
            id=new_id("cons"),
            summary=f"{patch.key} {delta:+d}: {patch.reason}".strip(),
            source_id=patch.character_id,
            reason=patch.reason,
            weight=float(delta),
        )
    )
    # Deterministic presence trigger: a vital stat (health) hitting its floor knocks the
    # character out (unconscious — the reversible lane; never auto-dead). Only fires once
    # (a still-present character), so a lingering health=0 doesn't re-emit every turn.
    definition = next(
        (sd for sd in stats.list_stat_definitions(db, ctx.storyline_id) if sd.key == patch.key),
        None,
    )
    member = ctx.cast_by_id(character_id)
    if definition is not None and member is not None and member.is_present:
        new_status = presence.vital_status_for(definition, value)
        if new_status:
            yield from _apply_presence_change(
                emitter, member, new_status, f"{patch.key} reached {value}", auto=True, tracer=tr
            )
    return abs(delta)
