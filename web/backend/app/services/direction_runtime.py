"""Direction runtime — what the player's direction still owes, mid-turn.

Split out of ``turn_engine`` so the loop module is an orchestrator rather than a library
(the owner's structural call, 2026-08-21). ``direction_agent`` *parses* a direction into
requirements; this module is the runtime half that runs against a turn in flight:

* :func:`delivered` — mark the requirements a beat carried into its prompt.
* :func:`direction_lead` — hand the next beat the outcomes it owes.
* :func:`plan_still_valid` — decide whether the planner's lookahead survived reality
  diverging from it (a character left, presence changed, the direction took the schedule
  over), which is what makes the ReAct loop re-plan instead of executing a stale plan.

NOTE for ``docs/plans/steering-the-scene.md`` Phase 2, which planned to create this module:
it already exists, with exactly the slice that plan named. Extend it rather than re-creating
it, and do not move these back into ``turn_engine``.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator

from sqlalchemy.orm import Session

from app.agents import planner_agent
from app.agents.direction_agent import DirectionRequirement, SceneDirection
from app.events.stream import TurnTraceFrame
from app.services.assembler import TurnContext
from app.agents import direction_agent
from app.agents.intent_agent import TurnIntent
from app.schemas.play import TurnRequest
from app.services.turn_emit import Tracer

def delivered(
    tracer: Tracer, ctx: TurnContext, direction: SceneDirection, owed: list[DirectionRequirement],
    *, by: str | None = None,
) -> Iterator[TurnTraceFrame]:
    """Mark requirements delivered AND say so on the wire.

    The engine already tracked what the turn still owed the player; it just never
    reported the ticking-off, so a direction's progress was invisible until the turn
    ended. ``by`` is the character who carried them (``None`` → the narrator).
    """
    if not owed:
        return
    direction.satisfy(owed)
    who = name_of(ctx, by) or "The narrator"
    yield from tracer.emit(
        "direction",
        f"{who} delivered {len(owed)} part(s) of your direction",
        detail="; ".join(r.text for r in owed),
        data={
            "delivered": [r.text for r in owed],
            "characterId": by,
            "outstanding": [r.text for r in direction.outstanding()],
        },
    )




def direction_lead(
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


def plan_still_valid(
    ctx: TurnContext,
    decision: planner_agent.BeatDecision,
    *,
    locked_id: str | None,
) -> bool:
    """Is a beat the planner decided *earlier* still runnable now?

    Planning ahead trades one LLM call for a prediction, and the prediction can go stale
    inside the same turn: a character can be cut down, walk out, or have a vital stat
    bottom out between the plan and its turn to speak. ``narrate`` and ``end`` are always
    runnable; anything naming a character is only runnable while that character is still
    present.

    A beat naming the POV character is deliberately **not** filtered here — the loop's own
    backstop handles that case, and it says so on the wire instead of dropping the beat
    silently.
    """
    del locked_id  # see the docstring: the POV backstop is the loop's, not this check's
    if decision.action in ("narrate", "end"):
        return True
    if decision.actor_id is None:
        return False
    member = ctx.cast_by_id(decision.actor_id)
    return member is not None and member.is_present
def name_of(ctx: TurnContext, character_id: str | None) -> str | None:
    """The cast member's display name for a trace payload (``None`` → the narrator)."""
    member = ctx.cast_by_id(character_id) if character_id else None
    return member.name if member is not None else None


def build_direction(
    db: Session,
    ctx: TurnContext,
    req: TurnRequest,
    *,
    intent: TurnIntent,
    pov_id: str | None,
    text: str,
    tracer: Tracer,
) -> Generator[TurnTraceFrame, None, SceneDirection]:
    """Resolve what the player directed this turn, and trace it.

    Moved out of the turn's opening so there is **one owner** of the direction, rather than
    the setup module holding a copy of logic this module then grows. `turn_setup.prepare_turn`
    drives it with ``yield from``.
    """
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
    elif pov_id is None and intent.requirements:
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
    return direction
