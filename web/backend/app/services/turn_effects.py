"""Turn effects — the consequences a beat may declare, validated then applied.

Split out of ``beat_runner`` so a beat's *generation* and its *effects* are separate
concerns (the owner's structural call, 2026-08-21). A speaker may propose a stat change, a
presence change or a relationship edge; nothing here trusts the model — each is validated
against the cast, the stat schema and the graph registry before it is applied, and an
unknown one is dropped rather than guessed at.

This module is a leaf: it depends on no other part of the turn loop.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator

from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.events.envelope import StoryEvent
from app.events.stream import TurnTraceFrame
from app.services import presence, session_stats, stats, validator
from app.services.assembler import CastMember, TurnContext
from app.services.turn_emit import Emitter, Tracer
from app.services.turn_writer import Consequence


def apply_declared_presence(
    ctx: TurnContext,
    character_id: str,
    raw: str,
    emitter: Emitter,
    tracer: Tracer,
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
    yield from apply_presence_change(emitter, member, status, reason, auto=True, tracer=tracer)


# Plain-language trace copy per presence transition (falls back to the free-text reason).

_PRESENCE_DETAIL = {
    "unconscious": "Knocked out — present but can't act until revived.",
    "departed": "No longer an active participant (body remains).",
    "left": "Walked out of the scene.",
    "dead": "Removed from the scene — permanently.",
    "present": "Back in the scene.",
}



def apply_presence_change(
    emitter: Emitter,
    member: CastMember,
    status: str,
    reason: str,
    *,
    auto: bool,
    tracer: Tracer,
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


def apply_relationship_change(
    ctx: TurnContext,
    source_id: str,
    raw: str,
    consequences: list[Consequence],
    tracer: Tracer,
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


def apply_stat_change(
    db: Session,
    ctx: TurnContext,
    character_id: str,
    raw: str,
    emitter: Emitter,
    consequences: list[Consequence],
    *,
    tracer: Tracer | None = None,
) -> Generator[StoryEvent | TurnTraceFrame, None, int]:
    """Validate + clamp a proposed stat change, apply it (hot path), emit, and record it.

    Returns the change's impact (``|delta|``, ``0`` when dropped) so the live queue can
    scale its re-rank + cascade to how much the beat actually moved.
    """
    tr = tracer or Tracer(False)
    patch = validator.validate_stat(
        db, ctx.storyline_id, character_id, raw, session_id=ctx.session_id
    )
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
    # Written to THIS play-through, so a branch or a rewind of another one is untouched.
    session_stats.apply(db, ctx.session_id, patch.character_id, {patch.key: value})
    # An author who marked a stat `hidden` meant it: the change is persisted (so the
    # Inspector, the export and a rewind's replay all still see it) and simply not streamed.
    # `Emitter.emit` already declines to yield a hidden event, so nothing new is needed here
    # beyond asking the definition what it wants. Before this, `visibility` had no effect at
    # play time at all and a hidden stat announced itself in the transcript.
    definition = next(
        (d for d in ctx.stat_defs if d.key == patch.key), None
    )
    hidden = bool(definition is not None and definition.visibility == "hidden")
    yield from emitter.emit(
        "state_update",
        {"patch": {}, "stat": patch.model_dump(by_alias=True)},
        visibility="hidden" if hidden else None,
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
            yield from apply_presence_change(
                emitter, member, new_status, f"{patch.key} reached {value}", auto=True, tracer=tr
            )
    return abs(delta)
