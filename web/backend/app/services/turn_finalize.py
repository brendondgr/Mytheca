"""Turn finalize — the tail every turn runs once its beats are done.

Split out of ``turn_engine`` (``docs/plans/control-over-the-record.md``) to keep the loop
module under the repo's file-length ceiling, and because none of this is part of *deciding*
a turn: by the time it runs, every beat has been emitted. It offers the follow-up
suggestions, hands the turn's durable consequences to the cold-path writer, dispatches the
reflection interlude, and stamps the session freshly played.

A pure move: ordering is unchanged, and it matters — the graph write happens before
reflection so a character reflects against a committed world.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy.orm import Session

from app.agents import director_agent
from app.events.envelope import StoryEvent
from app.events.stream import TurnTraceFrame
from app.models import Scenario
from app.schemas.play import TurnRequest
from app.services import events_store, reflection, relationships, turn_writer
from app.services.assembler import TurnContext
from app.services.turn_emit import Emitter, Tracer
from app.services.turn_writer import Consequence


def turn_summary(turn_beats: list[dict]) -> str:
    """A one-line summary of the turn for the appended :Event node."""
    parts = [str(b.get("text", "")).strip() for b in turn_beats if b.get("text")]
    return " · ".join(parts)[:240]



def finalize_turn(
    db: Session,
    *,
    scenario: Scenario,
    req: TurnRequest,
    ctx: TurnContext,
    session: Any,
    seq0: int,
    emitter: Emitter,
    tracer: Tracer,
    turn_beats: list[dict],
    consequences: list[Consequence],
    pov: Any,
    acted: bool,
    asked_question: bool,
    needs_branch: bool,
) -> Generator[StoryEvent | TurnTraceFrame, None, None]:
    """Close out a turn: suggestions, the cold-path graph write, reflection, recency."""
    # Follow-up suggestions: offer up to ``scenario.suggestions_count`` (0 disables) direct
    # follow-ups to the most recent line at the end of every turn — count-driven, no longer
    # gated on the planner's rarely-set ``needsBranch`` flag (which left the feature dead).
    # ``needs_branch`` now only colors the trace copy. Stats inform which options surface,
    # but never gate the choice mechanically (no dice — D11).
    branches: list[dict] = []
    # A question already IS the turn's fork; stacking generic follow-ups under it buries it.
    suggestions_count = 0 if asked_question else max(0, min(scenario.suggestions_count, 4))
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
        summary=turn_summary(turn_beats),
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
