"""Turn setup — everything a turn does before its first beat.

Split out of ``turn_engine`` (``docs/plans/control-over-the-record.md``) so the work of
*opening* a turn can be run without running the beat loop. That is what makes a single-beat
re-roll possible: a re-run needs the same session, context, POV, emitter and tracer the
original beat had, and rebuilding them meant either replaying the whole turn or copying the
setup into a second place where the two could drift.

:func:`prepare_turn` is a **generator**: it yields the opening diagnostic trace frames and
*returns* a :class:`TurnSetup`, so a caller drives it with ``setup = yield from
prepare_turn(...)``. This is a pure move — the ordering of side effects (assemble against
committed history, THEN record the player's line, THEN push the buffer) is unchanged, and
that ordering is load-bearing: the POV cast member has to be resolved before anything is
written.
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.agents import intent_agent
from app.agents.direction_agent import SceneDirection
from app.agents.intent_agent import TurnIntent
from app.events.stream import TurnTraceFrame
from app.memory import buffer
from app.models import Scenario
from app.schemas.play import TurnRequest
from app.services import (
    assembler,
    direction_runtime,
    events_store,
    history_compaction,
    settings_store,
    turn_settings,
)
from app.services.assembler import CastMember, TurnContext
from app.services.turn_emit import Emitter, Tracer
from app.services.turn_writer import Consequence




@dataclass
class TurnSetup:
    """Everything the beat loop needs, assembled before the first beat is generated."""

    session: Any
    text: str
    seq0: int
    ctx: TurnContext
    pov: CastMember | None
    pov_id: str | None
    tracer: Tracer
    emitter: Emitter
    #: The chronological this-turn transcript handed to each speaker, so a later speaker
    #: genuinely reacts to its predecessor. Seeded with the POV character's own line.
    turn_beats: list[dict] = field(default_factory=list)
    #: Durable consequences implied by the turn, routed off the hot path by turn_writer.
    consequences: list[Consequence] = field(default_factory=list)
    intent: Any = None
    direction: SceneDirection = field(default_factory=SceneDirection)
    show_reasoning: bool = False
    #: What this turn actually runs with — the scene's controls with the request's per-turn
    #: overrides on top. Resolved once, here, so the beat loop and the assembler cannot end
    #: up reading different answers for the same control.
    settings: turn_settings.TurnSettings | None = None


def prepare_turn(
    db: Session, scenario: Scenario, req: TurnRequest
) -> Generator[TurnTraceFrame, None, TurnSetup]:
    """Open a turn: resolve the session, assemble context, resolve POV, record the player's
    line, and read the scene's intent and direction. Yields trace frames; returns the setup."""
    session = events_store.resolve_session(db, scenario.id, req.session_id)
    text = (req.text or "").strip()

    seq0 = events_store.next_seq(db, session.id)
    # The tracer persists every diagnostic step (keyed by this turn's opening seq) so the
    # scene's graph/RAG activity is reviewable later; it still only *streams* when opted in.
    tracer = Tracer(
        req.trace, db=db, session_id=session.id, scenario_id=scenario.id, turn=seq0
    )

    # Assemble against committed history FIRST (read-only), so the Player POV member can be
    # resolved before anything is recorded, THEN push the player's line so it becomes
    # history for the next turn (the current line also seeds this turn's transcript, so it
    # is present even when the buffer is disabled).
    # Fold whatever has fallen out of the context window into the scene's memory, BEFORE the
    # assembler reads the session row. Compaction writes; the assembler is read-only, and
    # keeping that true is what lets the assembler be called from re-roll and replay paths
    # without side effects.
    compaction = history_compaction.maybe_compact(db, session, scenario)

    # The scene's controls with this turn's overrides on top. Resolved once, before anything
    # reads one: `beat_length` has to reach the assembler, `max_turns` the beat loop and
    # `suggestions_count` the tail, and resolving per-site is how one of the three quietly
    # keeps honouring the scenario row.
    settings = turn_settings.resolve(scenario, req.overrides)
    applied_overrides = turn_settings.applied(req.overrides)

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
    # Is the player a person in the scene this turn? Under POV, yes — their line is their
    # character's own beat and the cast may address them. Under Playwright mode they write
    # what happens from outside the fiction, so nobody in the room can see them. Set here,
    # once, because it cannot be resolved before `pov` is (it needs the roster to confirm the
    # character is actually present), and every downstream reader needs the same answer.
    ctx.player_embodied = pov is not None

    events_store.record_user_turn(
        db,
        scenario_id=scenario.id,
        session_id=session.id,
        seq=seq0,
        text=text,
        directed_at=req.directed_at,
        pov=pov_id,
        guidance=req.guidance,
        tagged_doc_ids=req.tagged_doc_ids,
        overrides=applied_overrides,
    )
    # A turn with no line from the player at all. The row is still written — the turn keeps
    # its trace grouping (traces are keyed by this seq) and its place in the export — but
    # everything downstream that assumed a player line has to be told there is not one.
    #
    # **This plan owns this branch.** `docs/plans/steering-the-scene.md` Phase 3 extended
    # this same one for a guidance-only turn — the trace `detail` falls back to the direction
    # text, so a direction-only turn shows what was asked for rather than a blank row. There
    # is deliberately no second branch: "the player said nothing" is one condition, and the
    # direction is what varies inside it.
    silent = not text
    guidance = (req.guidance or "").strip()
    # A direction-only turn (no line, but a direction) is a *different* thing from pressing
    # Continue, and the Inspector row must say so — otherwise the one row that records what
    # the player asked for reads "no line from you" and shows nothing they typed.
    directed_only = silent and bool(guidance)
    if not silent:
        turn_title = "You submitted a message"
    elif directed_only:
        turn_title = "You directed the scene"
    else:
        turn_title = "You let the scene continue"
    yield from tracer.emit(
        "turn",
        turn_title,
        detail=text or guidance or "No line from you this turn — the scene carries on.",
        data={
            "directedAt": req.directed_at,
            "mode": req.mode,
            "pov": pov_id,
            "continuation": bool(req.continuation),
            "directionOnly": directed_only,
            # Only what this turn actually overrode, so the Inspector row says what the
            # turn ran with rather than restating the scene's settings on every turn.
            **({"overrides": applied_overrides} if applied_overrides else {}),
        },
    )

    # Push the player's line into the recent-turn buffer as history for next turn — as the
    # POV character's own line when POV is active (so later speakers react to "Mei said X"),
    # else as an ordinary player line.
    # Nothing to push when the player said nothing: a blank entry would sit in the
    # transcript window as an empty player beat and poison every later prompt with it.
    if silent:
        pass
    elif pov is not None:
        buffer.push_turn(session.id, "character", text, character_id=pov.id)
    else:
        buffer.push_turn(session.id, "player", text)
    if compaction.ran:
        yield from tracer.emit(
            "compaction",
            f"Older beats folded into the scene's memory ({compaction.beats_folded})",
            detail=(
                "These beats no longer fit the model's context window, so what happened in "
                "them is kept as a summary the cast still reads."
            ),
            data={
                "beatsFolded": compaction.beats_folded,
                "throughSeq": compaction.through_seq,
                "summaryChars": compaction.summary_chars,
            },
        )
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
            "windowBeats": ctx.window_beats,
            "windowSource": ctx.window_source,
            "droppedBeats": ctx.dropped_beats,
            "budgetTokens": ctx.window_budget_tokens,
        },
    )
    # How far back the scene reached, as its own step. The player used to *set* this number
    # and never learn what it cost; now the app sets it and reports it, which is the right way
    # round — the depth is a consequence of the model's window, not a preference.
    yield from tracer.emit(
        "window",
        f"The scene reached back {ctx.window_beats} beat(s)",
        detail=(
            f"Fitted to the model's context window ({ctx.window_source})."
            + (
                f" {ctx.dropped_beats} older beat(s) did not fit."
                if ctx.dropped_beats
                else " Everything so far fitted."
            )
            if ctx.window_source != "fixed"
            else "This scene sets its own depth (context policy: fixed)."
        ),
        data={
            "windowBeats": ctx.window_beats,
            "windowSource": ctx.window_source,
            "droppedBeats": ctx.dropped_beats,
            "budgetTokens": ctx.window_budget_tokens,
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

    emitter = Emitter(db, scenario.id, session.id, start_seq=seq0 + 1)
    # The chronological this-turn transcript handed to each speaker so a later speaker
    # genuinely reacts to its predecessor (sequential by nature — §9). Under Player POV the
    # player's line seeds as the POV character's OWN beat (later speakers react to it as
    # "Mei said X"); the visible character event is intentionally WITHHELD — the client
    # already renders the player's line optimistically / on rehydrate, exactly as the plain
    # player line is today.
    if silent:
        # No player line to carry into this turn's transcript. The first speaker reacts to
        # the scene as it already stands rather than to an empty beat.
        turn_beats: list[dict] = []
    elif pov is not None:
        turn_beats = [{"role": "character", "text": text, "characterId": pov.id}]
    else:
        turn_beats = [{"role": "player", "text": text, "characterId": None}]

    # Durable consequences implied by the turn (populated from state_update events in
    # the branch/stat phase); routed off the hot path by the cold-path turn-writer.
    consequences: list[Consequence] = []

    # Whether the model's raw deliberation streams to the player this turn. Resolved once
    # (a settings read per beat would be wasteful) and threaded down to every generation.
    show_reasoning = settings_store.get_llm(db).reasoning_visibility == "full"

    # Interpret the player's line: narrating, addressing someone, or DIRECTING a character
    # to act/speak (puppet)? This is what fixes attribution (Reactive Turn Director D1) —
    # a puppeted character performs the direction in its own voice; the addressed character
    # reacts, instead of a bystander answering the player's words.
    # Announce the step BEFORE the call, not after it. The trace steps were all emitted
    # once their work was already done, so the status strip could only ever name the step
    # the turn had just finished — leaving the actual waits unlabelled.
    if settings.scene_mode == "freetext":
        # Free-text schedules nobody, so there is nothing for a classification to decide.
        # `intent.kind` picks puppets and addressees, and `intent.requirements` become the
        # direction the planner paces — and that engine is not running. Making the call
        # anyway would spend a round trip per turn on an answer nothing reads.
        #
        # The player's line still steers the turn; it does it by being in the prompt, which
        # is where the checklist call and the writer both read it from.
        intent = TurnIntent(
            directive=text or guidance or "The scene continues without the player speaking."
        )
    elif silent:
        # Nothing was said, so there is nothing to interpret. Skipping the call is not just a
        # saved LLM round-trip (though on the turn path that matters): asking the intent agent
        # to classify an empty string invites it to invent an ask the player never made.
        intent = TurnIntent(
            directive=(
                "The player did not speak; their direction alone steers this turn."
                if directed_only
                else "The scene continues without the player speaking."
            )
        )
    else:
        yield from tracer.emit(
            "reading",
            "Reading your message",
            detail="Working out whether you are narrating, addressing someone, or directing.",
        )
        intent = intent_agent.interpret(db, ctx, text, locked_id=pov_id)
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
        (
            ("Nothing was said — your direction steers the turn" if directed_only
             else "Nothing was said — the scene carries on")
            if silent
            else f"Read your intent: {intent.kind}"
        ),
        detail=intent.directive,
        data={
            "kind": intent.kind,
            "actors": [m.name for cid in intent.directed_actors if (m := ctx.cast_by_id(cid))],
            "addressed": [m.name for cid in intent.addressed if (m := ctx.cast_by_id(cid))],
            "scope": intent.scope,
        },
    )

    if settings.scene_mode == "freetext":
        # Same argument as the intent call above, and one step further: a direction is a
        # SCHEDULE — an ordered list of requirements paced across a beat budget, re-owed
        # across turns, and delivered by the beat the engine assigns them to. Free-text has
        # no beats to pace them across. The checklist is what stands in its place, and
        # parsing the same instruction twice into two competing contracts is how they end up
        # disagreeing about what the turn owes.
        direction = SceneDirection()
    else:
        direction = yield from direction_runtime.build_direction(
            db, ctx, req, intent=intent, pov_id=pov_id, text=text, tracer=tracer,
            session=session, turn=seq0,
        )

    return TurnSetup(
        session=session,
        text=text,
        seq0=seq0,
        ctx=ctx,
        pov=pov,
        pov_id=pov_id,
        tracer=tracer,
        emitter=emitter,
        turn_beats=turn_beats,
        consequences=consequences,
        intent=intent,
        direction=direction,
        show_reasoning=show_reasoning,
        settings=settings,
    )


def context_for_replay(
    db: Session, scenario: Scenario, session_id: str, *, through_seq: int
) -> tuple[TurnContext, list[dict]]:
    """Rebuild the context a beat originally saw, for a re-roll.

    ``prepare_turn`` cannot be re-run for this: it would record a **second** ``user_turn``
    row, push the player's line into the buffer again, and spend another intent call. What a
    re-roll needs is narrower — the same :class:`TurnContext`, and the same ``turn_beats``
    the target beat was generated against.

    ``through_seq`` is the last beat the re-run may see, i.e. the one **before** the target.
    Walking the persisted rows rather than the Redis buffer is deliberate: the buffer is a
    window, and the beat being re-rolled may already have fallen out of it. It is passed
    **into** the assembler for the opposite reason: left to itself the assembler takes its
    transcript window straight off that buffer, which still holds the beat being replaced.
    """
    ctx = assembler.assemble_context(
        db, scenario, session_id, None, player_text="", through_seq=through_seq
    )
    turn_beats: list[dict] = []
    rows = events_store.session_events(db, session_id)
    # The turn this beat belongs to opens at the last `user_turn` at or before it.
    opening_seq = 0
    for row in rows:
        if row.type == "user_turn" and row.seq <= through_seq:
            opening_seq = row.seq
    for row in rows:
        if row.seq < opening_seq or row.seq > through_seq:
            continue
        data = row.data if isinstance(row.data, dict) else {}
        text = str(data.get("text") or "").strip()
        if not text:
            continue
        if row.type == "user_turn":
            pov = data.get("pov")
            # A re-roll has to rebuild the point of view the beat was originally written
            # under, not the one in force now. The player may have switched modes since, and
            # re-rolling a Playwright beat as though they were embodied would put a "you"
            # into a scene they are not standing in.
            ctx.player_embodied = bool(pov)
            turn_beats.append(
                {
                    "role": "character" if pov else "player",
                    "text": text,
                    "characterId": pov or None,
                }
            )
        elif row.type in ("narration",):
            turn_beats.append({"role": "narrator", "text": text, "characterId": None})
        elif row.type in ("character_prose", "character_dialogue", "character_action"):
            turn_beats.append(
                {
                    "role": "character",
                    "text": text,
                    "characterId": data.get("characterId"),
                }
            )
    return ctx, turn_beats
