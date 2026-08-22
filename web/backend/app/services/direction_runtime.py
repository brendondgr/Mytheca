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
from sqlalchemy import select

from app.models import Character, PlaySession, Scenario
from app.services.assembler import TurnContext
from app.agents import direction_agent
from app.agents.intent_agent import TurnIntent
from app.core.config import get_settings
from app.schemas.play import TurnRequest
from app.services import direction_check
from app.services.turn_emit import Tracer

# ---- carry-over: a direction outlives the turn it rode in on ----------------


def load_standing(session: PlaySession) -> list[DirectionRequirement]:
    """The requirements a previous turn could not deliver, oldest debt first.

    Rebuilt from the session's stored list rather than from the ``direction`` trace rows: a
    turn's correctness must not depend on diagnostics being retained, and traces are the
    first thing an operator prunes. Malformed rows are skipped rather than raising — a bad
    JSON blob must not be able to take a play-through down.
    """
    rows = session.standing_direction if isinstance(session.standing_direction, list) else []
    out: list[DirectionRequirement] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        out.append(
            DirectionRequirement(
                id=str(row.get("id") or f"std{len(out) + 1}"),
                text=text,
                actor_id=row.get("actorId") or None,
                pinned=bool(row.get("pinned")),
                from_turn=row.get("fromTurn") if isinstance(row.get("fromTurn"), int) else None,
            )
        )
    return out


def merge_standing(
    direction: SceneDirection, standing: list[DirectionRequirement], *, turn: int
) -> SceneDirection:
    """Put what the player is still owed **ahead of** what they just asked for.

    Oldest debt first, because a requirement that has already survived a turn is the one
    most at risk of never landing — and because the player asked for it first. Duplicates
    (the same text asked for again) collapse onto the standing entry, so re-stating a
    direction does not double the debt. Capped at ``MAX_REQUIREMENTS``: past that the extras
    would be bundled into one packed beat anyway, which reads worse than deferring them, so
    the newest are dropped and the debt is kept.
    """
    if not standing:
        return direction
    seen = {r.text.strip().lower() for r in standing}
    fresh = [r for r in direction.requirements if r.text.strip().lower() not in seen]
    merged = [*standing, *fresh][: direction_agent.MAX_REQUIREMENTS]
    for req in merged:
        if req.from_turn is None and req in standing:
            req.from_turn = turn
    text = direction.text.strip()
    if not text:
        # A turn with no direction of its own still owes the debt, and the debt IS the
        # direction for that turn — otherwise `active` is False and nothing schedules it.
        text = "\n".join(r.text for r in merged)
    return SceneDirection(text=text, requirements=merged)


def to_standing(direction: SceneDirection, *, turn: int) -> list[dict]:
    """Everything not delivered, as rows for ``PlaySession.standing_direction``.

    ``fromTurn`` is stamped on the way out so a requirement carries the turn it was *first*
    asked for, not the turn it most recently failed on — the checklist's "carried over"
    badge is about age, and re-stamping it every turn would make an old debt look new.
    """
    return [
        {
            "id": r.id,
            "text": r.text,
            "actorId": r.actor_id,
            "pinned": r.pinned,
            "fromTurn": r.from_turn if r.from_turn is not None else turn,
        }
        for r in direction.requirements
        if not r.delivered
    ]


def save_standing(db: Session, session: PlaySession, rows: list[dict]) -> None:
    """Write the debt back, clearing the column to ``None`` when nothing is owed."""
    session.standing_direction = rows or None
    db.add(session)
    db.flush()


# ---- asking for someone who is not here -------------------------------------


def _storyline_character_ids(db: Session, storyline_id: str) -> set[str]:
    """Every character id in this world — the namespace a directive may aim at."""
    return set(
        db.scalars(select(Character.id).where(Character.storyline_id == storyline_id)).all()
    )


def cast_requests(
    db: Session, ctx: TurnContext, scenario: Scenario, direction: SceneDirection
) -> list[tuple[Character, str]]:
    """The absent storyline characters this direction named, and why.

    **The AI never introduces a character on its own initiative.** There is no planner action
    that brings someone in; this only turns "the player named someone who is not here" into a
    question. Two sources, neither costing an LLM call:

    * a **pinned** requirement whose actor is absent (Phase 8's ``blocked`` state) — the
      player explicitly aimed a line at them;
    * a plain **longest-first name match** of the direction text against the storyline's
      absent character names — the same matcher the composer's ``@`` menu uses, run here so
      writing "Kael bursts in" works without needing to know the mention syntax.

    Anyone with a ``character_status_change`` already on this session is excluded, so a
    character the player has **declined** is never asked about again, and one already brought
    in is not asked about at all.

    Returns ``(character, reason)`` in the order they were named, at most one per character.
    """
    text = direction.text.lower()
    present_or_answered = {m.id for m in ctx.cast}
    out: list[tuple[Character, str]] = []
    seen: set[str] = set()

    def offer(char: Character, reason: str) -> None:
        if char.id in seen or char.id in present_or_answered:
            return
        seen.add(char.id)
        out.append((char, reason))

    # Explicit pins first — the player aimed a requirement at this person by name.
    for req in direction.requirements:
        if not (req.blocked and req.actor_id):
            continue
        char = db.get(Character, req.actor_id)
        if char is not None and char.storyline_id == scenario.storyline_id:
            offer(char, req.text)

    # Then a plain name match over the rest of the storyline. Longest name first, so
    # "Wren Calloway" wins over a character called "Wren".
    if text:
        others = [
            c
            for c in db.scalars(
                select(Character).where(Character.storyline_id == scenario.storyline_id)
            )
            if c.id not in present_or_answered
        ]
        for char in sorted(others, key=lambda c: -len(c.name or "")):
            name = (char.name or "").strip().lower()
            if name and name in text:
                # Quote the requirement that mentions them, so the ask shows the player
                # their own words rather than a generic prompt.
                reason = next(
                    (r.text for r in direction.requirements if name in r.text.lower()),
                    direction.text,
                )
                offer(char, reason)
    return out


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
def name_of(
    ctx: TurnContext, character_id: str | None, db: Session | None = None
) -> str | None:
    """The character's display name for a trace payload (``None`` → the narrator).

    ``db`` widens the lookup past the scene's cast. A **blocked** requirement names, by
    definition, someone who is not in the room — so resolving only through ``ctx.cast`` would
    make the one trace whose whole job is to say *who* the scene is waiting for unable to say
    it.
    """
    if not character_id:
        return None
    member = ctx.cast_by_id(character_id)
    if member is not None:
        return member.name
    if db is not None:
        char = db.get(Character, character_id)
        if char is not None:
            return char.name
    return None


def build_direction(
    db: Session,
    ctx: TurnContext,
    req: TurnRequest,
    *,
    intent: TurnIntent,
    pov_id: str | None,
    text: str,
    tracer: Tracer,
    session: PlaySession | None = None,
    turn: int = 0,
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
    # Directives bind against the whole **storyline**, not just the scene's cast. A player
    # can legitimately aim a line at someone who is not in the room ("@Kael bursts in"), and
    # that is precisely the case worth keeping: it pins to Kael, `rebind` marks it blocked
    # rather than handing it to the narrator, and `cast_requests` turns it into an offer to
    # bring them in. Narrowing to the present cast would drop the target on the floor and
    # make the whole blocked/request path unreachable.
    cast_ids = _storyline_character_ids(db, ctx.storyline_id)
    directives = [(d.text, d.actor_id) for d in req.directives if (d.text or "").strip()]
    if directives:
        # The player wrote the targets themselves. Nothing left to infer, so no LLM call.
        direction = direction_agent.from_directives(directives, cast_ids)
        source = "directives"
    elif guidance:
        direction = direction_agent.parse(db, ctx, guidance)
        source = "guidance"
    elif pov_id is None and intent.requirements:
        direction = SceneDirection(text=intent.directive or text, requirements=intent.requirements)
        source = "message"
    else:
        direction = SceneDirection()
        source = "message"
    # What a previous turn could not deliver is owed before anything asked for now.
    standing = load_standing(session) if session is not None else []
    if standing:
        direction = merge_standing(direction, standing, turn=turn)
        yield from tracer.emit(
            "direction",
            f"{len(standing)} part(s) of an earlier direction are still owed",
            detail="; ".join(r.text for r in standing),
            data={
                "carried": [
                    {"id": r.id, "text": r.text, "fromTurn": r.from_turn} for r in standing
                ]
            },
        )
    direction.rebind({m.id for m in ctx.cast if m.is_present}, locked_id=pov_id)
    if direction.active:
        yield from tracer.emit(
            "direction",
            f"You directed the scene ({len(direction.requirements)} thing(s) to deliver)",
            detail=direction.text,
            data={
                "source": source,
                "requirements": [
                    {
                        "text": r.text,
                        "actor": name_of(ctx, r.actor_id, db),
                        "pinned": r.pinned,
                        **({"fromTurn": r.from_turn} if r.from_turn is not None else {}),
                    }
                    for r in direction.requirements
                ],
            },
        )
        yield from report_blocked(tracer, ctx, direction, db)
    return direction


def report_blocked(
    tracer: Tracer, ctx: TurnContext, direction: SceneDirection, db: Session | None = None
) -> Iterator[TurnTraceFrame]:
    """Say which pinned requirements are waiting on a character who is not in the scene.

    Without this the requirement would look identical to one the turn simply never got to,
    and the player would have no way to tell "the scene ran out of beats" from "the person
    you named is not here". It is also the hook Phase 9 attaches its offer to.
    """
    waiting = [r for r in direction.requirements if r.blocked and not r.delivered]
    if not waiting:
        return
    for name, reqs in _by_actor(ctx, waiting, db).items():
        yield from tracer.emit(
            "direction",
            f"{name} is not in the scene — {len(reqs)} part(s) of your direction wait",
            detail="; ".join(r.text for r in reqs),
            data={
                "blocked": [r.text for r in reqs],
                "characterId": reqs[0].actor_id,
                "characterName": name,
            },
        )


def _by_actor(
    ctx: TurnContext, requirements: list[DirectionRequirement], db: Session | None = None
) -> dict[str, list[DirectionRequirement]]:
    """Group requirements by their bound character's display name, order preserved."""
    out: dict[str, list[DirectionRequirement]] = {}
    for req in requirements:
        name = name_of(ctx, req.actor_id, db) or "Someone"
        out.setdefault(name, []).append(req)
    return out
