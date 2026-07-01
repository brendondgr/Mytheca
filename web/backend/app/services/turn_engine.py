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

from collections.abc import Generator, Iterator
from typing import Any

from sqlalchemy.orm import Session

from app.agents import (
    character_turn_agent,
    director_agent,
    intent_agent,
    narrator_agent,
    planner_agent,
)
from app.agents._common import resolve_llm
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


class _Tracer:
    """Interleaves diagnostic :class:`TurnTraceFrame`s when the caller opts in.

    Off by default: when disabled, :meth:`emit` yields nothing, so the stream and the
    story-event contract are unchanged. When enabled it stamps a per-turn ordinal ``n``
    so the Inspector can render the steps in the exact order they happened.
    """

    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled
        self._n = 0

    def emit(
        self,
        step: str,
        title: str,
        *,
        detail: str = "",
        data: dict[str, Any] | None = None,
    ) -> Iterator[TurnTraceFrame]:
        if not self._enabled:
            return
        self._n += 1
        yield TurnTraceFrame(n=self._n, step=step, title=title, detail=detail, data=data or {})


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
    tracer = _Tracer(req.trace)

    seq0 = events_store.next_seq(db, session.id)
    events_store.record_user_turn(
        db,
        scenario_id=scenario.id,
        session_id=session.id,
        seq=seq0,
        text=text,
        directed_at=req.directed_at,
    )
    yield from tracer.emit(
        "turn",
        "You submitted a message",
        detail=text,
        data={"directedAt": req.directed_at, "mode": req.mode},
    )

    # Assemble against committed history, THEN push the player's line so it becomes
    # history for the next turn (the current line also seeds this turn's transcript,
    # so it is present even when the buffer is disabled).
    ctx = assembler.assemble_context(db, scenario, session.id, req.directed_at, player_text=text)
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

    emitter = _Emitter(db, scenario.id, session.id, start_seq=seq0 + 1)
    # The chronological this-turn transcript handed to each speaker so a later speaker
    # genuinely reacts to its predecessor (sequential by nature — §9).
    turn_beats: list[dict] = [{"role": "player", "text": text, "characterId": None}]

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

    # Puppet beats first: each directed character performs the player's direction in its
    # OWN voice (not a reply to the player's words).
    puppet_members = [m for cid in intent.directed_actors if (m := ctx.cast_by_id(cid)) is not None]
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
        yield from _generate_speaker(
            db, ctx, speaker, emitter, turn_beats, consequences,
            guard_conn=guard_conn, directive=intent.directive, relationship_note=note, tracer=tracer,
        )

    # ReAct loop (D3): after each beat, re-decide the next one from the transcript so
    # far — which character acts (optionally addressing another), whether the narrator
    # sets context, or the turn ends. Unbounded by design — a whole-group direction walks
    # the entire cast (D2); TURN_MAX_BEATS is only a runaway backstop, and the ceiling
    # floors above the cast size so a large cast is never clipped.
    acted: list[str] = [m.id for m in puppet_members]
    max_beats = max(get_settings().turn_max_beats, 2 * len(ctx.cast) + 6)
    needs_branch = False
    beats = 0
    while beats < max_beats:
        decision = planner_agent.next_beat(db, ctx, intent, turn_beats, acted)
        if decision.action == "end":
            needs_branch = decision.needs_branch
            yield from tracer.emit(
                "plan", "The turn ends", detail=decision.reason or "The direction is satisfied."
            )
            break
        if decision.action == "narrate":
            yield from tracer.emit("plan", "The narrator sets the scene", detail=decision.reason)
            yield from _narrator_interstitial(db, ctx, turn_beats, emitter)
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
            data={"actor": actor.name, "addressing": addressing.name if addressing else None},
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
        yield from _generate_speaker(
            db, ctx, actor, emitter, turn_beats, consequences,
            guard_conn=guard_conn, relationship_note=note, tracer=tracer,
        )
        acted.append(actor.id)
        beats += 1
    else:
        yield from tracer.emit(
            "plan",
            "Reached the turn's beat limit",
            detail=f"Stopped after {beats} beats (runaway backstop).",
        )

    # Nobody spoke at all (no puppet, no planned beat) → a quiet holding narration.
    if not acted:
        yield from emitter.emit(
            "narration", {"text": "The scene waits, quiet.", "done": True}, buffer_role="narrator"
        )

    # A narrative fork: stats inform which options surface, but never gate the choice
    # mechanically (no dice — D11).
    branches: list[dict] = []
    if needs_branch:
        branches = director_agent.propose_branches(db, ctx, turn_beats)
        if branches:
            yield from emitter.emit("branch_choices", {"choices": branches})
            yield from tracer.emit(
                "branch",
                f"Offered {len(branches)} branch choice(s)",
                detail="A fork — pick one to steer where the scene goes next.",
                data={"choices": [b.get("label", "") for b in branches]},
            )

    # Cold path (Band 3): runs after the last event is yielded — never blocks the
    # player, best-effort, no-op when there are no consequences or the graph is down.
    yield from tracer.emit(
        "commit",
        (
            f"Committing {len(consequences)} change(s) to the story graph"
            if consequences
            else "Nothing durable to commit to the story graph"
        ),
        detail=(
            "Stat consequences + an :Event node are written to the knowledge graph (Neo4j) "
            "after the turn."
            if consequences
            else "This turn moved no stat/relationship, so the knowledge graph is unchanged."
        ),
        data={"consequences": len(consequences)},
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
    reflection_targets = ctx.cast if len(ctx.cast) > 2 else spoke
    reflection.dispatch_reflection(db, ctx, reflection_targets, turn_beats, branches=branches, seq=seq0)

    # First turn of a new session (D4 / P3): seed initial character↔character relationships
    # from the authored bios into the story graph (best-effort, idempotent, off the hot
    # path — a graph/LLM outage is a clean no-op). The cold path evolves them thereafter.
    if req.session_id is None:
        seeded = relationships.ensure_seeded(db, scenario)
        yield from tracer.emit(
            "relationships",
            f"Seeded {seeded} relationship(s) from bios" if seeded else "Relationships not seeded",
            detail=(
                "Initial character-to-character edges extracted from the cast's backgrounds "
                "into the story graph."
                if seeded
                else "Already seeded, the graph is off, or the bios implied none."
            ),
            data={"seeded": seeded},
        )
    yield from tracer.emit(
        "reflection",
        f"{len(reflection_targets)} character(s) reflect",
        detail=(
            "Each privately updates its stance for next turn"
            + (" (branch-keyed for the fork above)" if branches else "")
            + ("; the whole cast reflects in a crowd" if len(ctx.cast) > 2 else "")
            + "."
        ),
        data={"targets": [m.name for m in reflection_targets], "universal": len(ctx.cast) > 2},
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
    tracer: _Tracer | None = None,
) -> Generator[StoryEvent | TurnTraceFrame, None, int]:
    """Generate one speaker's beat, guard it for continuity, emit its events, append them
    to ``turn_beats``, and return the beat's impact (Σ|stat delta|) for the live queue.

    ``directive`` marks a **puppet** beat (the player directed this character): the
    character performs it in-voice and the continuity guard is skipped (there is nothing
    to contradict — the player asked for it). ``relationship_note`` folds the speaker's
    graph relationships (to whom they address, + 2-hop) into the prompt (D4)."""
    tr = tracer or _Tracer(False)
    roster = {i + 1: m.id for i, m in enumerate(ctx.cast)}
    raw = character_turn_agent.generate_line(
        db, ctx, speaker, turn_beats=turn_beats, directive=directive, relationship_note=relationship_note
    )
    segments = emission.parse_emission(raw, roster=roster, fallback_speaker_id=speaker.id)

    # Consistency guard (§P10): once a character has already spoken this turn, a later
    # line must not contradict the established beats. Regenerate once with the reason if
    # it does; best-effort (an unconfigured/failed guard leaves the line as-is).
    if guard_conn is not None and not directive and _has_prior_character_beat(turn_beats):
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
            raw = character_turn_agent.generate_line(
                db, ctx, speaker, turn_beats=turn_beats, correction=verdict.reason,
                relationship_note=relationship_note,
            )
            segments = emission.parse_emission(raw, roster=roster, fallback_speaker_id=speaker.id)

    impact = 0
    for seg in segments:
        if seg.type == "internal_thought":
            # Hidden conditioning — persisted, withheld, and NOT shown to later speakers,
            # but surfaced in the Inspector trace so the reasoning is visible there.
            yield from emitter.emit(
                "internal_thought",
                {"characterId": seg.character_id, "text": seg.text},
                visibility="hidden",
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
    return impact


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
    return abs(delta)
