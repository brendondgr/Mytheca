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

from app.agents import direction_agent, intent_agent
from app.agents.intent_agent import TurnIntent
from app.agents.direction_agent import SceneDirection
from app.events.stream import TurnTraceFrame
from app.memory import buffer
from app.models import Scenario
from app.schemas.play import TurnRequest
from app.services import assembler, events_store, settings_store
from app.services.assembler import CastMember, TurnContext
from app.services.turn_emit import Emitter, Tracer
from app.services.turn_writer import Consequence


def name_of(ctx: TurnContext, character_id: str | None) -> str | None:
    """The cast member's display name for a trace payload (``None`` → the narrator)."""
    member = ctx.cast_by_id(character_id) if character_id else None
    return member.name if member is not None else None




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
        guidance=req.guidance,
        tagged_doc_ids=req.tagged_doc_ids,
    )
    # A turn with no line from the player at all. The row is still written — the turn keeps
    # its trace grouping (traces are keyed by this seq) and its place in the export — but
    # everything downstream that assumed a player line has to be told there is not one.
    #
    # **This plan owns this branch.** `docs/plans/steering-the-scene.md` Phase 3 extends the
    # same one for a guidance-only turn (falling `detail` back to the direction text); it
    # must not add a second.
    silent = not text
    yield from tracer.emit(
        "turn",
        "You let the scene continue" if silent else "You submitted a message",
        detail=text or "No line from you this turn — the scene carries on.",
        data={
            "directedAt": req.directed_at,
            "mode": req.mode,
            "pov": pov_id,
            "continuation": bool(req.continuation),
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
    if silent:
        # Nothing was said, so there is nothing to interpret. Skipping the call is not just a
        # saved LLM round-trip (though on the turn path that matters): asking the intent agent
        # to classify an empty string invites it to invent an ask the player never made.
        intent = TurnIntent(directive="The scene continues without the player speaking.")
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
        "Nothing was said — the scene carries on" if silent else f"Read your intent: {intent.kind}",
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
                    {"text": r.text, "actor": name_of(ctx, r.actor_id)}
                    for r in direction.requirements
                ],
            },
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
    )
