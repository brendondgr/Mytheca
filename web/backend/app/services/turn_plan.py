"""Plan mode — showing a turn's plan, and running one the player approved.

Planning already happened on every turn; what this module adds is the two things a player
can do with the result. Under ``PlannerMode`` ``"plan"`` the turn stops after planning and
streams a :class:`TurnPlanFrame`; the player approves it and sends it straight back on
``TurnRequest.approvedPlan``, and :func:`from_approved` turns it into the decisions the loop
executes **without re-planning**. Under ``"auto"`` the same frame is emitted and nothing
stops — the Inspector still gets to show what the turn decided.

Split out of ``turn_engine`` rather than added to it: the engine was one line under the
800-line ceiling before this feature and 886 after, and the ceiling exists precisely so that
"just a bit more" in the orchestrator is a decision somebody has to make rather than one that
happens by accident.

Two rules the module exists to keep in one place:

* **An approved plan is executed, never re-planned.** A second planner call would produce a
  different turn from the one the player agreed to, which is the entire failure the feature
  exists to prevent.
* **A plan is never a story event.** It states what a turn *intends*, which may not happen.
  Persisting one would put something in the transcript that no reader ever saw and that no
  rewind could account for — so it rides as a transport frame, like ``trace`` and
  ``reasoning``.
"""

from __future__ import annotations

from app.agents import planner_agent
from app.events.stream import PlannedBeat, TurnPlanFrame
from app.schemas.play import ApprovedBeat
from app.services import direction_runtime
from app.services.assembler import TurnContext


def plan_frame(
    ctx: TurnContext,
    decisions: list[planner_agent.BeatDecision],
    *,
    awaiting_approval: bool,
) -> TurnPlanFrame:
    """Render planner decisions as the wire's plan frame.

    Actor ids are resolved to **names** here rather than left for the client to join against
    the cast. The frame is read by a person, and a panel that has to look three ids up to
    draw three rows is a panel that draws "unknown" the first time presence changes.
    """
    beats = [
        PlannedBeat(
            action=d.action,
            actorId=d.actor_id,
            actorName=(member.name if (member := _member(ctx, d.actor_id)) else ""),
            addressingId=d.addressing_id,
            reason=d.reason,
            register=d.register,
            stakes=d.stakes,
            status=d.status,
        )
        for d in decisions
    ]
    return TurnPlanFrame(
        sessionId=ctx.session_id, beats=beats, awaitingApproval=awaiting_approval
    )


def _member(ctx: TurnContext, actor_id: str | None):
    return ctx.cast_by_id(actor_id) if actor_id else None


def from_approved(
    ctx: TurnContext,
    approved: list[ApprovedBeat],
    *,
    locked_id: str | None,
) -> list[planner_agent.BeatDecision]:
    """The plan the player approved, as decisions the loop can run.

    **Roster-checked even though the player approved it.** Presence can change between a plan
    being shown and it coming back — a character can be written out by the turn that produced
    the plan, and the player may sit on the panel for a minute — so a beat naming somebody who
    has since left is dropped rather than run. Approving a plan approves its intent, not a
    licence to voice a character who is no longer in the scene.

    Everything else is carried through verbatim, register and stakes included, because those
    are what the player was shown and what the prose will be written against.
    """
    decisions = [
        planner_agent.BeatDecision(
            action=row.action,
            actor_id=row.actor_id,
            addressing_id=row.addressing_id,
            reason=row.reason,
            register=row.beat_register,
            stakes=row.stakes,
            status=row.status,
        )
        for row in approved
    ]
    return [
        d for d in decisions if direction_runtime.plan_still_valid(ctx, d, locked_id=locked_id)
    ]


def may_ask(
    db,
    session_id: str,
    *,
    before_seq: int,
    scene_opening: bool,
    narrated_open: bool,
    direction_active: bool,
    puppeted: bool,
) -> bool:
    """Whether the planner is allowed to stop and put a question to the player this turn.

    The conditions are the ENGINE'S, not the model's, and that is the point: a planner that
    may ask will ask too often, and a scene that stops moving is worse than a mediocre guess.
    So permission is withheld unless nothing has happened yet this turn (a question after the
    scene has moved is answering nothing), the player's line is freeform rather than a
    direction the turn already owes, and the previous turn did not already stop to ask.
    """
    return (
        not scene_opening
        and not narrated_open
        and not direction_active
        and not puppeted
        and not _ended_on_a_question(db, session_id, before_seq)
    )


def _ended_on_a_question(db, session_id: str, before_seq: int) -> bool:
    from app.services import events_store

    return events_store.ended_on_a_question(db, session_id, before_seq=before_seq)


def preflight(
    db,
    ctx: TurnContext,
    intent,
    turn_beats: list[dict],
    acted: list[str],
    tracer,
    *,
    approved: list[ApprovedBeat],
    mode: str,
    lookahead: int,
    scene_opening: bool,
    locked_id: str | None,
    direction,
    beat_budget: int,
    trace: bool,
):
    """Everything plan mode does *before* the beat loop. Yields frames; returns a verdict.

    ``("stop", [])`` — the turn planned and is waiting for approval. The caller returns
    immediately: no prose, no suggestions, no reflection.

    ``("run", [decisions])`` — an approved plan, ready to execute with no planner call.

    ``("continue", [])`` — an ordinary turn; the loop plans for itself as it always has.

    Both halves run here, before the loop, because both are about the turn as a whole: a plan
    shown mid-turn plans the rest of something already committed, and an approval arriving
    mid-turn approves beats that have already happened.
    """
    if approved:
        planned = from_approved(ctx, approved, locked_id=locked_id)
        if not planned:
            # Every approved beat named somebody who is no longer selectable. Falling through
            # to ordinary planning is the right recovery — the alternative is a turn that
            # answers the player with silence — but it is NOT what they approved, so it is
            # traced as the substitution it is rather than passed off as their plan.
            yield from tracer.emit(**stale_trace())
            return "continue", []
        yield from tracer.emit(**approved_trace(planned))
        return "run", planned
    if mode != "plan":
        return "continue", []
    proposal = planner_agent.plan_beats(
        db, ctx, intent, turn_beats, acted, lookahead=max(lookahead, 4),
        scene_opening=scene_opening, locked_id=locked_id,
        direction=direction, remaining_beats=beat_budget,
    )
    yield from tracer.emit(**awaiting_trace(proposal))
    # Sent regardless of `trace`: under this mode the frame is not diagnostics, it is the
    # mechanism — without it the player has nothing to approve and the turn simply stops dead.
    yield plan_frame(ctx, proposal, awaiting_approval=True)
    return "stop", []


def observe(ctx: TurnContext, planned, *, trace: bool):
    """The plan frame for an ordinary ``auto`` turn — **only when tracing**.

    A plan is worth showing in the Inspector, and worth nothing to a client that did not ask
    for diagnostics. Emitting it unconditionally would also insert a frame ahead of the first
    story event on **every** turn, which quietly changes the shape of the default stream that
    `docs/api-contract.md` documents and that every existing consumer indexes into. Same
    opt-in as ``TurnTraceFrame``, for the same reason.
    """
    if trace and planned:
        yield plan_frame(ctx, planned, awaiting_approval=False)


def approved_trace(planned: list[planner_agent.BeatDecision]) -> dict:
    """The Inspector row for a turn running an approved plan — ``tracer.emit(**...)``.

    Keyword arguments rather than a tuple, because ``Tracer.emit`` takes ``detail`` and
    ``data`` keyword-only; a positional splat would land ``detail`` in nothing at all.
    """
    return {
        "step": "planning",
        "title": f"Running the plan you approved ({len(planned)} beat(s))",
        "detail": (
            "No planner call: this is the plan you were shown and agreed to, and re-planning "
            "it would produce a different turn."
        ),
        "data": {"planner": "approved", "beats": len(planned)},
    }


def stale_trace() -> dict:
    """The Inspector row for an approved plan that nobody in it can act on any more."""
    return {
        "step": "planning",
        "title": "The plan you approved is out of date",
        "detail": (
            "Everyone it named has left the scene since you approved it, so none of it could "
            "be run. The scene planned this turn afresh instead of answering you with silence."
        ),
        "data": {"planner": "stale"},
    }


def awaiting_trace(proposal: list[planner_agent.BeatDecision]) -> dict:
    """The Inspector row for a turn that stopped for approval — ``tracer.emit(**...)``."""
    return {
        "step": "planning",
        "title": f"Planned {len(proposal)} beat(s) — waiting for you",
        "detail": (
            "Nothing has been written. Approve the plan to play it out, or change your "
            "direction and send again."
        ),
        "data": {"planner": "plan", "beats": len(proposal)},
    }
