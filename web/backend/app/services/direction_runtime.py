"""Direction runtime — what the player's direction still owes, mid-turn.

Split out of ``turn_engine`` so the loop module is an orchestrator rather than a library
(the owner's structural call, 2026-08-21). ``direction_agent`` *parses* a direction into
requirements; this module is the runtime half that runs against a turn in flight:

* :func:`attempted` / :func:`confirm` — the two halves of "did the direction land?".
  A beat *attempts* the requirements it carries into its prompt; delivery is confirmed
  afterwards, from the prose it actually emitted.
* :func:`pace` — how many of the outstanding requirements one beat should take on.
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
from app.core.config import get_settings
from app.schemas.play import TurnRequest
from app.services import direction_check
from app.services.turn_emit import Tracer

def max_attempts() -> int:
    """How many beats may attempt one requirement before the turn stops re-owing it."""
    return max(1, get_settings().direction_max_attempts)


def beat_text_since(turn_beats: list[dict], mark: int) -> str:
    """The prose a beat actually emitted, read off the this-turn transcript.

    Every emitting path — a character's passage, a narrator interstitial — appends its text
    to ``turn_beats``. A beat that produced nothing (an empty generation, a withheld
    scratchpad leak, a failed request) appends nothing, so this returns ``""`` and the
    requirement is simply never confirmed. That one fact fixes the largest cause of a
    direction being "forgotten", with no heuristic involved.

    Reading the transcript rather than widening four return signatures keeps the confirm
    step out of the beat runners entirely: they already record what they emitted.
    """
    return " ".join(str(b.get("text") or "") for b in turn_beats[mark:]).strip()


def pace(owed: list[DirectionRequirement], remaining: int) -> int:
    """How many of ``owed`` one beat should take on, given ``remaining`` beats.

    One per beat while there is room; more only when the budget forces it. The old code
    used a fixed ``[:1]`` slice at the per-beat sites and an all-or-one switch at the
    opening, so a five-part direction with two beats left put one part on this beat and
    hoped — which is how the tail of a long direction went missing.
    """
    if not owed:
        return 0
    return max(1, -(-len(owed) // max(1, remaining)))


def attempted(
    tracer: Tracer, ctx: TurnContext, direction: SceneDirection, owed: list[DirectionRequirement],
    *, by: str | None = None,
) -> Iterator[TurnTraceFrame]:
    """Record that a beat is carrying ``owed`` into its prompt, and say so on the wire.

    This is a *promise*, not an outcome — which is precisely the distinction the engine used
    to lose. ``by`` is the character who carries them (``None`` → the narrator).
    """
    if not owed:
        return
    direction.attempt(owed)
    who = name_of(ctx, by) or "The narrator"
    yield from tracer.emit(
        "direction",
        f"{len(owed)} part(s) of your direction ride on {who.lower() if by is None else who}'s beat",
        detail="; ".join(r.text for r in owed),
        data={
            "attempted": [r.text for r in owed],
            "characterId": by,
            "outstanding": [r.text for r in direction.outstanding(max_attempts())],
        },
    )


def confirm(
    tracer: Tracer,
    ctx: TurnContext,
    direction: SceneDirection,
    owed: list[DirectionRequirement],
    beat_text: str,
    *,
    by: str | None = None,
) -> Iterator[TurnTraceFrame]:
    """Confirm which of ``owed`` the beat's prose actually reached.

    Called **after** the beat with the text it emitted. A beat that produced nothing
    confirms nothing and the requirements stay outstanding — no heuristic needed for the
    failure cases, which are the common ones. For a beat that *did* produce prose, the
    lexical check in :mod:`app.services.direction_check` decides, with the bound actor's own
    name excluded from the requirement's words: a requirement reads "Mei snaps back" while
    Mei's own in-voice beat never says "Mei".
    """
    if not owed:
        return
    if not beat_text:
        yield from tracer.emit(
            "direction",
            "That beat delivered nothing, so your direction still stands",
            detail="; ".join(r.text for r in owed),
            data={
                "unconfirmed": [r.text for r in owed],
                "characterId": by,
                "outstanding": [r.text for r in direction.outstanding(max_attempts())],
            },
        )
        return
    threshold = get_settings().direction_coverage_threshold
    ignore = [n] if (n := name_of(ctx, by)) else []
    landed = [
        r
        for r in owed
        if direction_check.reached(r.text, beat_text, threshold=threshold, ignore_names=ignore)
    ]
    missed = [r for r in owed if r not in landed]
    direction.satisfy(landed)
    who = name_of(ctx, by) or "The narrator"
    if landed:
        yield from tracer.emit(
            "direction",
            f"{who} delivered {len(landed)} part(s) of your direction",
            detail="; ".join(r.text for r in landed),
            data={
                "delivered": [r.text for r in landed],
                "unconfirmed": [r.text for r in missed],
                "characterId": by,
                "outstanding": [r.text for r in direction.outstanding(max_attempts())],
            },
        )
    if missed:
        retrying = [r for r in missed if r.attempts < max_attempts()]
        yield from tracer.emit(
            "direction",
            (
                f"{len(missed)} part(s) may not have landed — trying again"
                if retrying
                else f"{len(missed)} part(s) could not be confirmed"
            ),
            detail="; ".join(r.text for r in missed),
            data={
                "unconfirmed": [r.text for r in missed],
                "characterId": by,
                "outstanding": [r.text for r in direction.outstanding(max_attempts())],
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
