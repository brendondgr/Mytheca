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

from app.agents import character_turn_agent, director_agent, narrator_agent
from app.agents._common import resolve_llm
from app.agents.reflection_agent import LlmConn
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
    reflection,
    stats,
    turn_writer,
    validator,
)
from app.services.assembler import CastMember, TurnContext
from app.services.turn_writer import Consequence

# A high-impact beat (Σ|stat delta| at/above this) moves the whole room: the cascade
# refreshes every remaining speaker's disposition. A smaller shift only nudges the very
# next speaker (§P10 — "width/strength scaled to impact").
_CASCADE_WIDE_THRESHOLD = 10


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

    decision = director_agent.who_is_up(db, ctx)
    speakers = [m for cid in decision.speakers if (m := ctx.cast_by_id(cid)) is not None]
    yield from tracer.emit(
        "director",
        f"The Director chose {len(speakers)} speaker(s)",
        detail=_director_rationale(decision, speakers),
        data={
            "speakers": [m.name for m in speakers],
            "beat": decision.beat,
            "needsBranch": decision.needs_branch,
        },
    )
    if not speakers:
        yield from tracer.emit(
            "director", "No one speaks", detail="No character was picked; the scene simply holds."
        )
        yield from emitter.emit(
            "narration", {"text": "The scene waits, quiet.", "done": True}, buffer_role="narrator"
        )
        return

    # Multi-party turns get a continuity guard (a later line can't contradict an
    # established beat) and a live queue (a high-impact beat re-ranks who is up next and
    # cascades a disposition refresh). Solo turns skip both. The guard connection is
    # resolved once — the LLM is already configured (generation would have failed first).
    guard_conn = _resolve_conn(db) if len(ctx.cast) > 1 else None

    index = 0
    while index < len(speakers):
        speaker = speakers[index]
        yield from tracer.emit(
            "speaker",
            f"{speaker.name} responds",
            detail=f"Speaker {index + 1} of {len(speakers)} this turn.",
            data={"characterId": speaker.id, "name": speaker.name},
        )
        # Narrator Mode: a transition beat before the speaker (POV Mode: off — D1).
        if req.mode == "narrator":
            yield from _narrator_interstitial(db, ctx, turn_beats, emitter)
        impact = yield from _generate_speaker(
            db, ctx, speaker, emitter, turn_beats, consequences, guard_conn=guard_conn, tracer=tracer
        )
        remaining = speakers[index + 1 :]
        if impact > 0 and remaining:
            # Mid-turn re-consult: re-rank the not-yet-spoken speakers after the shift.
            before = [m.name for m in remaining]
            reordered_ids = director_agent.rerank(db, ctx, [m.id for m in remaining], turn_beats)
            reordered = [m for cid in reordered_ids if (m := ctx.cast_by_id(cid)) is not None]
            speakers[index + 1 :] = reordered
            after = [m.name for m in reordered]
            if after != before:
                yield from tracer.emit(
                    "rerank",
                    "Re-ranked who speaks next",
                    detail=f"A strong beat (impact {impact}) shifted the order.",
                    data={"from": before, "to": after},
                )
            # Cascade the disposition refresh, width scaled to impact — a bigger shift
            # moves more of the room; a small one only the very next speaker.
            width = len(reordered) if impact >= _CASCADE_WIDE_THRESHOLD else 1
            reflection.refresh_dispositions(db, ctx, reordered[:width], turn_beats, seq=seq0)
            yield from tracer.emit(
                "cascade",
                f"Refreshed {min(width, len(reordered))} character(s)' stance",
                detail="They re-evaluate their mood mid-turn before speaking.",
                data={"targets": [m.name for m in reordered[:width]], "impact": impact},
            )
        index += 1

    # A narrative fork (after the line-to-line consistency pass seam): stats inform
    # which options surface, but never gate the choice mechanically (no dice — D11).
    branches: list[dict] = []
    if decision.needs_branch:
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
    reflection_targets = ctx.cast if len(ctx.cast) > 2 else speakers
    reflection.dispatch_reflection(db, ctx, reflection_targets, turn_beats, branches=branches, seq=seq0)
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


def _director_rationale(decision: "director_agent.DirectorDecision", speakers: list[CastMember]) -> str:
    """A plain-language "why these speakers" line for the Inspector."""
    names = ", ".join(m.name for m in speakers) or "no one"
    beat = decision.beat
    if beat == "addressed":
        return f"You addressed {names} directly, so only they respond."
    if beat == "solo":
        return f"{names} is the only character present, so they respond."
    if beat == "empty":
        return "No characters are in the scene."
    if beat == "fallback":
        return (
            "The Director couldn't reason a choice (the model was unavailable), so the first "
            f"character ({names}) responds."
        )
    return (
        f"The Director read the moment ('{beat}') and picked who is most provoked to react, "
        f"in order: {names}."
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
    tracer: _Tracer | None = None,
) -> Generator[StoryEvent | TurnTraceFrame, None, int]:
    """Generate one speaker's beat, guard it for continuity, emit its events, append them
    to ``turn_beats``, and return the beat's impact (Σ|stat delta|) for the live queue."""
    tr = tracer or _Tracer(False)
    roster = {i + 1: m.id for i, m in enumerate(ctx.cast)}
    raw = character_turn_agent.generate_line(db, ctx, speaker, turn_beats=turn_beats)
    segments = emission.parse_emission(raw, roster=roster, fallback_speaker_id=speaker.id)

    # Consistency guard (§P10): once a character has already spoken this turn, a later
    # line must not contradict the established beats. Regenerate once with the reason if
    # it does; best-effort (an unconfigured/failed guard leaves the line as-is).
    if guard_conn is not None and _has_prior_character_beat(turn_beats):
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
                db, ctx, speaker, turn_beats=turn_beats, correction=verdict.reason
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
