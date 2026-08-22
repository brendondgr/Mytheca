"""Turn engine — the runtime story loop.

Drives one player turn: persist the ``user_turn``, assemble Band-1 context, run the
per-character POV loop (one isolated LLM call per active speaker), and stream the
visible story events as NDJSON while persisting each.

Visible prose (``narration`` / ``character_dialogue``) **delta-streams**: the same
event (same id + seq) is emitted with incremental ``text`` + ``done: false`` until the
last chunk sets ``done: true`` (the client accumulates by id; the persisted row holds
the full text). ``character_action`` streams as one full event; ``internal_thought``
(``visibility: private_to_user``) streams to the player as a distinct "thinking" bubble
but is kept OUT of ``turn_beats`` — later speakers never condition on it. ``Emitter``
centralizes the seq + persist + buffer + withhold-hidden plumbing every phase reuses.

Speaker selection is a **ReAct loop with lookahead**: ``planner_agent.plan_beats`` decides
the next few beats (``speak`` / ``narrate`` / ``exit`` / ``end``) from the *present* roster
in one call, with the POV character locked out, and the loop executes them until the plan
runs out or reality diverges from it — a character exits, presence changes, the direction
takes the schedule over — at which point it re-plans. ``TURN_PLANNER_LOOKAHEAD`` sets the
depth (1 restores the original once-per-beat behaviour). The loop is bounded by the scene's ``max_turns`` and a
runaway backstop of ``max(TURN_MAX_BEATS, 2 * len(cast) + 6)``. This replaced the earlier
one-shot director (``director_agent.who_is_up`` / ``rerank``), which is now dead code kept
only for its unit tests.

Over that loop sits the **scene direction** (Narrator-Guided Scenes): when the player is
directing — their own line in narrator mode, the separate ``guidance`` box under Player POV
— the turn owes a list of ``direction_agent`` requirements. The planner sees what is still
owed and how many beats are left; once the budget is as tight as the direction is long the
engine stops asking and runs ``direction_agent.schedule`` itself, so everything asked for
lands inside ``scenario.max_turns``. Each beat carries only *its* requirements into the
prompt, as an outcome to reach — the speaker still chooses their own words and stays in
character.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.agents import (
    direction_agent,
    planner_agent,
)
from app.core.config import get_settings
from app.core.errors import APIError
from app.events.envelope import StoryEvent
from app.events.stream import TurnTraceFrame
from app.models import Scenario
from app.schemas.play import TurnRequest
from app.services import (
    crud,
    events_store,
)

from app.services import beat_runner
from app.services import turn_setup
from app.services import direction_runtime
from app.services import turn_effects
from app.services import turn_finalize



def validate_turn_inputs(db: Session, scenario_id: str, req: TurnRequest) -> Scenario:
    """Pre-flight (before the 200 stream opens): scenario exists, the turn asks for
    *something*, session valid.

    A turn used to require ``text``, which made the player's own line the only way to move a
    scene: you could not direct without also speaking, and you could not simply let the scene
    run. It is now valid when **any** of four things is present:

    * ``text`` — the player speaks (or narrates);
    * ``guidance`` — the player directs without speaking;
    * ``outcome`` — the player took a branch;
    * ``continuation`` — the player pressed *Continue* and is just watching.

    **This function states that whole rule once, and this plan owns it.**
    ``docs/plans/steering-the-scene.md`` Phase 3 *consumes* the ``guidance`` arm for its
    direction-only turn and must not re-open this function; ``outcome`` is included here for
    the same reason even though nothing sends it yet. One edit, one rule, one place it can
    drift from.
    """
    scenario = crud.get_scenario(db, scenario_id)  # raises 404 when missing
    asks_for_something = (
        (req.text or "").strip()
        or (req.guidance or "").strip()
        or (req.outcome or "").strip()
        or req.continuation
    )
    if not asks_for_something:
        raise APIError(
            400, "bad_request", "Say something, direct the scene, or press Continue."
        )
    if req.session_id:
        events_store.resolve_session(db, scenario_id, req.session_id)  # validates only
    return scenario


def run_turn(
    db: Session, scenario: Scenario, req: TurnRequest
) -> Iterator[StoryEvent | TurnTraceFrame]:
    """Run one turn, yielding the visible story events (and, when ``req.trace``, the
    interleaved diagnostic trace frames the Inspector renders) in order."""
    setup = yield from turn_setup.prepare_turn(db, scenario, req)
    # Unpacked into locals so the beat loop below reads exactly as it did before the split.
    session = setup.session
    seq0 = setup.seq0
    ctx = setup.ctx
    pov = setup.pov
    pov_id = setup.pov_id
    tracer = setup.tracer
    emitter = setup.emitter
    turn_beats = setup.turn_beats
    consequences = setup.consequences
    intent = setup.intent
    direction = setup.direction
    show_reasoning = setup.show_reasoning

    # Narration leads, before anyone speaks. Two cases (feedback #1/#2/#3):
    #  • Branch continuation — the player picked a narrative direction (``outcome``): open
    #    with a fuller "progression" paragraph that plays the choice out, then let the
    #    scene react below.
    #  • Cold scene open with NO direction — the narrator sets the moment and the turn is
    #    narrator-only (no character talks unprompted); the character loop is skipped.
    outcome = (req.outcome or "").strip()
    scene_opening = not ctx.recent_beats  # nothing committed before this turn
    narrated_open = False

    # Ask about anyone the player named who is not in the scene. This is a QUESTION, never
    # an arrival: the AI has no way to bring a character in, and presence moves only when the
    # player answers through the ordinary manual path. Emitted before any beat so the offer
    # is on screen while the turn plays out rather than arriving after it.
    for guest, reason in direction_runtime.cast_requests(db, ctx, scenario, direction):
        yield from tracer.emit(
            "direction",
            f"The scene is asking for {guest.name}",
            detail=reason,
            data={"castRequest": guest.id, "characterName": guest.name},
        )
        yield from emitter.emit(
            "cast_request", {"characterId": guest.id, "reason": reason}
        )
    # Per-scene hard ceiling on the beats a single player message produces (Scene Dialogue
    # Updates). The planner may still end the turn earlier; this only caps a drawn-out
    # exchange. The ceiling counts EVERY emitted beat — character replies AND narrator beats
    # (request #3) — so a hard cap of N is never exceeded: the scene-setting narrated open
    # and any puppet performances count toward it, as does each mid-turn interstitial.
    # Resolved here (rather than beside the loop) because the opening narration below has to
    # know how much of the direction it must absorb.
    max_turns = max(1, scenario.max_turns)
    # How many beats may attempt one requirement before the turn stops re-owing it. Read
    # once: it bounds every `outstanding`/`for_actor` call below, and a requirement that
    # answered a different cap in two places would flicker in and out of the owed list.
    attempt_cap = direction_runtime.max_attempts()
    # How much of the narrator's share the opening beat takes on. This used to be an
    # all-or-one switch — every narrator-owned requirement at once when the direction was
    # longer than the scene, otherwise exactly one — which is how the tail of a long
    # direction went missing in the middle band. `pace` spreads them against the real beat
    # budget instead: one per beat while there is room, more only when the budget forces it.
    open_limit = direction_runtime.pace(direction.for_actor(None, attempt_cap), max_turns)
    if outcome:
        yield from tracer.emit(
            "plan", "The narrator plays out your choice", detail=outcome, data={"outcome": outcome}
        )
        owed = direction.for_actor(None, attempt_cap)[:open_limit]
        yield from direction_runtime.attempted(tracer, ctx, direction, owed)
        mark = len(turn_beats)
        narrated_open = yield from beat_runner.narrator_interstitial(
            db, ctx, turn_beats, emitter, show_reasoning=show_reasoning,
            lead=direction_runtime.direction_lead(direction, owed, base=outcome), long=True,
        )
        yield from direction_runtime.confirm(
            tracer, ctx, direction, owed, direction_runtime.beat_text_since(turn_beats, mark)
        )
    elif scene_opening and not intent.directed_actors and not intent.addressed and intent.scope != "all":
        yield from tracer.emit(
            "plan",
            "The narrator opens the scene",
            detail="Scene start — the narrator sets the moment before anyone responds.",
        )
        owed = direction.for_actor(None, attempt_cap)[:open_limit]
        yield from direction_runtime.attempted(tracer, ctx, direction, owed)
        mark = len(turn_beats)
        narrated_open = yield from beat_runner.narrator_interstitial(
            db, ctx, turn_beats, emitter, show_reasoning=show_reasoning,
            lead=direction_runtime.direction_lead(direction, owed, base="Open the scene."), long=True,
        )
        yield from direction_runtime.confirm(
            tracer, ctx, direction, owed, direction_runtime.beat_text_since(turn_beats, mark)
        )

    # Puppet beats first: each directed character performs the player's direction in its
    # OWN voice (not a reply to the player's words). The POV character is excluded — the
    # player already voiced them this turn, so the AI must not perform a second beat for them.
    puppet_members = [
        m
        for cid in intent.directed_actors
        if (m := ctx.cast_by_id(cid)) is not None and m.id != pov_id
    ]
    for speaker in puppet_members:
        yield from tracer.emit(
            "speaker",
            f"{speaker.name} performs your direction",
            detail=intent.directive,
            data={"characterId": speaker.id, "name": speaker.name, "puppet": True},
        )
        note = beat_runner.relationship_note(
            ctx, speaker.id, intent.addressed or [m.id for m in ctx.cast if m.id != speaker.id]
        )
        if note:
            yield from tracer.emit("relationship", f"{speaker.name}'s ties", detail=note, data={"characterId": speaker.id})
        # A puppeted character performs the direction, so their own requirements ride on the
        # very beat the player asked for rather than waiting for a later one.
        owed = direction.for_actor(speaker.id, attempt_cap)
        yield from direction_runtime.attempted(tracer, ctx, direction, owed, by=speaker.id)
        mark = len(turn_beats)
        yield from beat_runner.generate_speaker(
            db, ctx, speaker, emitter, turn_beats, consequences,
            show_reasoning=show_reasoning, directive=intent.directive, relationship_note=note,
            direction=direction, requirements=owed, tracer=tracer,
        )
        yield from direction_runtime.confirm(
            tracer, ctx, direction, owed,
            direction_runtime.beat_text_since(turn_beats, mark), by=speaker.id,
        )

    # ReAct loop (D3): after each beat, re-decide the next one from the transcript so
    # far — which character acts (optionally addressing another), whether the narrator
    # sets context, or the turn ends. Unbounded by design — a whole-group direction walks
    # the entire cast (D2); TURN_MAX_BEATS is only a runaway backstop, and the ceiling
    # floors above the cast size so a large cast is never clipped.
    acted: list[str] = [m.id for m in puppet_members]
    # The POV character has already taken their beat (the player's line), so mark them acted:
    # a broadcast/crowd never re-selects them, and they still reflect at end-of-turn so their
    # interior stays current for when the AI takes them back over.
    if pov_id is not None:
        acted.append(pov_id)
    max_beats = max(get_settings().turn_max_beats, 2 * len(ctx.cast) + 6)
    scene_beats = len(puppet_members) + (1 if narrated_open else 0)
    # How many characters have actually spoken prose this turn (puppets included — the
    # player directed them, but they still took a beat). The exchange guard below reads it.
    spoke = len(puppet_members)
    # Character beats attempted this turn, and the ones that came back empty. Collected
    # rather than raised: whether the player sees an error is decided at the end, by whether
    # every attempt failed (see ``beat_runner.beat_or_skip``).
    tally: dict = {"attempts": 0, "failures": []}
    # The guard fires at most once a turn: it is there to stop a scene ending on a single
    # line, not to keep a conversation going by force.
    forced_exchange = False
    needs_branch = False
    # The turn stopped to ask the player where the story should go (planner "ask"). It is
    # the last word of the turn: no holding narration, no follow-up suggestions stacked
    # under it, and the next turn may not ask again.
    asked_question = False
    # When the planner is ALLOWED to ask. The conditions are the engine's, not the model's:
    # nothing has happened yet this turn (a question after the scene has moved is answering
    # nothing), the player's line is freeform rather than a direction the turn already owes,
    # and the previous turn did not already stop to ask. A planner that may ask will ask too
    # often, and a scene that stops moving is worse than a mediocre guess.
    may_ask = (
        not scene_opening
        and not narrated_open
        and not direction.active
        and not puppet_members
        and not events_store.ended_on_a_question(db, session.id, before_seq=seq0)
    )
    beats = 0
    # Beats the planner has decided but the loop has not run yet. The planner was 41 % of
    # all turn time purely because it ran once per beat (EXP-2026-08-005), so it is asked
    # for several at once and re-consulted only when this queue empties or is invalidated.
    planned: list[planner_agent.BeatDecision] = []
    lookahead = max(1, get_settings().turn_planner_lookahead)
    while beats < max_beats:
        # Presence can change mid-turn (an exit beat, a vital stat bottoming out), so re-own
        # any requirement whose character just left before scheduling against it.
        direction.rebind({m.id for m in ctx.cast if m.is_present}, locked_id=pov_id)
        outstanding = direction.outstanding(attempt_cap)
        remaining = max_turns - scene_beats
        if scene_beats >= max_turns:
            yield from tracer.emit(
                "plan",
                "Reached the scene's turn limit",
                detail=(
                    f"Stopped after {scene_beats} beat(s) (scene cap of {max_turns})."
                    + (
                        f" {len(outstanding)} part(s) of your direction did not fit —"
                        " raise the scene's turn limit to give it more room."
                        if outstanding
                        else ""
                    )
                ),
                data={"end": True, "undelivered": [r.text for r in outstanding]},
            )
            break
        # The direction is a contract, and the scene cap is hard — so once what is still owed
        # would fill every beat that is left, the planner's judgement can no longer be
        # afforded and the engine schedules the rest itself. Below that line the planner
        # decides freely, with the outstanding list and the budget in its prompt.
        decision: planner_agent.BeatDecision | None = None
        forced_reason = "the rest of your direction has to fit the beats that are left"
        if not outstanding or len(outstanding) < remaining:
            if not planned:
                depth = min(lookahead, max(1, remaining))
                yield from tracer.emit(
                    "planning",
                    "Deciding who speaks next" if depth == 1 else f"Planning the next {depth} beats",
                    detail=f"{remaining} beat(s) left in the scene's budget.",
                )
                planned = planner_agent.plan_beats(
                    db, ctx, intent, turn_beats, acted, lookahead=depth,
                    scene_opening=scene_opening and not narrated_open, locked_id=pov_id,
                    direction=direction if direction.active else None, remaining_beats=remaining,
                    may_ask=may_ask and beats == 0,
                )
            # A planned beat is a prediction, and presence can change under it — a character
            # who was cut down two beats ago must not be picked because a stale plan said so.
            while planned and not direction_runtime.plan_still_valid(ctx, planned[0], locked_id=pov_id):
                planned.pop(0)
            decision = planned.pop(0) if planned else None
            # An "end" while the player is still owed something is not the planner's call.
            if decision is not None and decision.action == "end" and outstanding:
                decision = None
                planned.clear()
                forced_reason = "your direction is not delivered yet"
        if decision is None:
            # The engine is taking the schedule over, so anything the planner had queued is
            # answering a question that no longer applies.
            planned.clear()
            scheduled = direction_agent.schedule(outstanding, remaining)
            if scheduled is None:
                break
            owed = scheduled.requirements
            yield from direction_runtime.attempted(
                tracer, ctx, direction, owed, by=scheduled.actor_id
            )
            forced_actor = ctx.cast_by_id(scheduled.actor_id) if scheduled.actor_id else None
            if forced_actor is None:
                yield from tracer.emit(
                    "direction",
                    "The narrator delivers your direction",
                    detail=forced_reason,
                    data={"requirements": [r.text for r in owed]},
                )
                mark = len(turn_beats)
                yield from beat_runner.narrator_interstitial(
                    db, ctx, turn_beats, emitter, show_reasoning=show_reasoning,
                    lead=direction_runtime.direction_lead(direction, owed),
                    # Several requirements bundled into one closing beat need a paragraph,
                    # not a two-sentence transition, to actually land them all.
                    long=len(owed) > 1,
                )
                yield from direction_runtime.confirm(
                    tracer, ctx, direction, owed,
                    direction_runtime.beat_text_since(turn_beats, mark),
                )
            else:
                yield from tracer.emit(
                    "direction",
                    f"{forced_actor.name} delivers your direction",
                    detail=forced_reason,
                    data={"characterId": forced_actor.id, "requirements": [r.text for r in owed]},
                )
                note = beat_runner.relationship_note(
                    ctx, forced_actor.id, [m.id for m in ctx.cast if m.id != forced_actor.id]
                )
                mark = len(turn_beats)
                played = yield from beat_runner.beat_or_skip(
                    tracer, forced_actor, tally,
                    db=db, ctx=ctx, emitter=emitter, turn_beats=turn_beats,
                    consequences=consequences,
                    show_reasoning=show_reasoning, relationship_note=note,
                    direction=direction, requirements=owed,
                )
                yield from direction_runtime.confirm(
                    tracer, ctx, direction, owed,
                    direction_runtime.beat_text_since(turn_beats, mark), by=forced_actor.id,
                )
                acted.append(forced_actor.id)
                spoke += 1 if played else 0
                scene_beats += 1 if played else 0
                beats += 1
                continue
            beats += 1
            scene_beats += 1
            continue
        # Defensive backstop (decision #1): the POV character is the player's to voice, never
        # the AI's. The planner already excludes them from the roster, but if a stray reply
        # ever names them, treat it as the turn ending rather than voicing a duplicate beat.
        if pov_id is not None and decision.action == "speak" and decision.actor_id == pov_id:
            yield from tracer.emit(
                "plan",
                "The turn ends",
                detail="The POV character is voiced by the player.",
                data={"end": True},
            )
            break
        if decision.action == "end":
            # A room with two people in it should not answer the player with one line and
            # stop. The owner's word for what is wanted is "back and forth", and the
            # ps_c015c506b1 export is the failure: two characters present, the player asks
            # for a moment between THEM, and the turn is Fennel alone followed by "the turn
            # ends — direction satisfied". Valdar never answers.
            #
            # So the planner's first `end` is refused once, when a present character has
            # not spoken at all and fewer than two have. Once only, and never when the cast
            # is a single character: this is a floor under the exchange, not a quota.
            others = [m for m in ctx.cast if m.is_present and m.id != pov_id]
            silent = [m for m in others if m.id not in acted]
            if not forced_exchange and spoke < 2 and silent and len(others) >= 2:
                forced_exchange = True
                planned.clear()
                responder = silent[0]
                yield from tracer.emit(
                    "speaker",
                    f"{responder.name} answers",
                    detail=(
                        "The turn would have ended on one line with someone still in the "
                        "room who had not spoken."
                    ),
                    # ``register``/``stakes`` ride on every speaker step so the client never
                    # has to guess whether the engine omitted them or the planner had
                    # nothing to say (an empty string means the latter).
                    data={
                        "characterId": responder.id,
                        "name": responder.name,
                        "exchange": True,
                        "register": decision.register or "",
                        "stakes": decision.stakes or "",
                    },
                )
                note = beat_runner.relationship_note(
                    ctx, responder.id, [m.id for m in ctx.cast if m.id != responder.id]
                )
                played = yield from beat_runner.beat_or_skip(
                    tracer, responder, tally,
                    db=db, ctx=ctx, emitter=emitter, turn_beats=turn_beats,
                    consequences=consequences,
                    show_reasoning=show_reasoning, relationship_note=note,
                    register=decision.register, stakes=decision.stakes,
                    direction=direction,
                )
                acted.append(responder.id)
                beats += 1
                # A beat that did not come back is not a beat the scene played: counting it
                # would tell the exchange guard and the silent-turn backstop that the player
                # has been answered when they have not.
                scene_beats += 1 if played else 0
                spoke += 1 if played else 0
                continue
            # Every step that stops the beat loop carries ``data.end = True`` — the
            # structured signal the story player's turn-status strip reads to say "the turn
            # is ending". The titles are prose and will drift; the flag will not.
            needs_branch = decision.needs_branch
            yield from tracer.emit(
                "plan",
                "The turn ends",
                detail=decision.reason or "The direction is satisfied.",
                data={"end": True},
            )
            break
        if decision.action == "ask":
            # The direction is genuinely open and guessing would commit the scene to
            # something the player never chose. Put the question to them and stop — it
            # rides on ``branch_choices`` so it renders and round-trips into the composer
            # through machinery that already works.
            asked_question = True
            yield from emitter.emit(
                "branch_choices",
                {
                    "prompt": decision.question,
                    "choices": [{"label": o, "outcome": ""} for o in decision.options],
                },
            )
            yield from tracer.emit(
                "plan",
                "Asking you where this goes",
                detail=decision.reason or decision.question,
                data={
                    "end": True,
                    "ask": True,
                    "question": decision.question,
                    "choices": decision.options,
                },
            )
            break
        if decision.action == "narrate":
            yield from tracer.emit("plan", "The narrator sets the scene", detail=decision.reason)
            # One narrator-owned requirement per narrated beat, so a multi-part direction
            # paces out across the turn instead of arriving as a single summary paragraph.
            narrator_owed = direction.for_actor(None, attempt_cap)
            owed = narrator_owed[: direction_runtime.pace(narrator_owed, remaining)]
            yield from direction_runtime.attempted(tracer, ctx, direction, owed)
            mark = len(turn_beats)
            yield from beat_runner.narrator_interstitial(
                db, ctx, turn_beats, emitter, show_reasoning=show_reasoning,
                lead=direction_runtime.direction_lead(direction, owed) or None,
            )
            yield from direction_runtime.confirm(
                tracer, ctx, direction, owed,
                direction_runtime.beat_text_since(turn_beats, mark),
            )
            beats += 1
            scene_beats += 1
            continue
        if decision.action == "exit":
            # The director removes a character the story already wrote out (dead/left/…).
            # Marks them non-present so no later beat picks them; a structural op that costs
            # a runaway-backstop beat but not the player's scene-turn budget.
            leaver = ctx.cast_by_id(decision.actor_id) if decision.actor_id else None
            if leaver is None or decision.status is None:
                break
            yield from tracer.emit(
                "plan",
                f"{leaver.name} exits the scene ({decision.status})",
                detail=decision.reason,
                data={"characterId": leaver.id, "status": decision.status},
            )
            yield from turn_effects.apply_presence_change(
                emitter, leaver, decision.status, decision.reason, auto=True, tracer=tracer
            )
            # The roster just changed shape, so anything planned against the old one is
            # answering the wrong question — re-plan rather than execute a stale queue.
            planned.clear()
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
            data={
                "actor": actor.name,
                "addressing": addressing.name if addressing else None,
                "register": decision.register,
                "stakes": decision.stakes or None,
            },
        )
        yield from tracer.emit(
            "speaker",
            f"{actor.name} responds",
            # The planner already decided WHY this character is up and how the beat is
            # pitched; carrying both into the trace lets the status strip answer the
            # commonest question in play — why them, and not the one I addressed?
            detail=decision.reason,
            data={
                "characterId": actor.id,
                "name": actor.name,
                "reason": decision.reason,
                "register": decision.register or "",
                "stakes": decision.stakes,
            },
        )
        note = beat_runner.relationship_note(
            ctx,
            actor.id,
            [addressing.id] if addressing else [m.id for m in ctx.cast if m.id != actor.id],
        )
        if note:
            yield from tracer.emit("relationship", f"{actor.name}'s ties", detail=note, data={"characterId": actor.id})
        # One of this actor's own requirements rides on the beat the planner chose for them
        # (the rest, if any, wait for a later beat or the forced schedule above).
        actor_owed = direction.for_actor(actor.id, attempt_cap)
        owed = actor_owed[: direction_runtime.pace(actor_owed, remaining)]
        yield from direction_runtime.attempted(tracer, ctx, direction, owed, by=actor.id)
        mark = len(turn_beats)
        played = yield from beat_runner.beat_or_skip(
            tracer, actor, tally,
            db=db, ctx=ctx, emitter=emitter, turn_beats=turn_beats,
            consequences=consequences,
            show_reasoning=show_reasoning, relationship_note=note,
            register=decision.register, stakes=decision.stakes,
            direction=direction, requirements=owed,
        )
        yield from direction_runtime.confirm(
            tracer, ctx, direction, owed,
            direction_runtime.beat_text_since(turn_beats, mark), by=actor.id,
        )
        acted.append(actor.id)
        beats += 1
        scene_beats += 1 if played else 0
        spoke += 1 if played else 0
    # A player who typed a line always gets a scene back. The beat loop can reach `end`
    # having produced nothing at all — a planner that misreads the moment, a fallback with
    # nobody selectable, an intent aimed at a character who cannot be chosen. Turns 8 and 9
    # of the ps_0bf9ddc13b session were exactly that: intent → planning → "the turn ends",
    # no prose, no explanation. The upstream causes are fixed above; this is the defence
    # that does not depend on having diagnosed all of them.
    # ``scene_beats`` counts only prose the ENGINE produced this turn — it starts at the
    # puppet beats plus a narrated open, and rises per beat. Deliberately not a scan of
    # ``turn_beats``: under Player POV the player's own line is seeded there as a character
    # beat, so that would read the player's own words back as "the scene answered".
    # A turn that stopped to ask the player a question is not silent — it is waiting, and
    # answering it with a beat would bury the question under the prose it was asked instead of.
    if scene_beats == 0 and not asked_question:
        responder = next(
            (m for m in ctx.cast if m.is_present and m.id != pov_id and m.id in intent.addressed),
            next((m for m in ctx.cast if m.is_present and m.id != pov_id), None),
        )
        if responder is not None:
            yield from tracer.emit(
                "speaker",
                f"{responder.name} responds",
                detail="Nothing had been played yet this turn — the scene answers rather than ending in silence.",
                data={
                    "characterId": responder.id,
                    "name": responder.name,
                    "backstop": True,
                    "register": "",
                    "stakes": "",
                },
            )
            note = beat_runner.relationship_note(
                ctx, responder.id, [m.id for m in ctx.cast if m.id != responder.id]
            )
            yield from beat_runner.beat_or_skip(
                tracer, responder, tally,
                db=db, ctx=ctx, emitter=emitter, turn_beats=turn_beats,
                consequences=consequences,
                show_reasoning=show_reasoning, relationship_note=note,
                direction=direction,
            )
            beats += 1
        elif ctx.cast:
            yield from tracer.emit(
                "plan",
                "The narrator carries the moment",
                detail="Nobody was selectable, so the scene is narrated rather than left blank.",
                data={"backstop": True},
            )
            yield from beat_runner.narrator_interstitial(
                db, ctx, turn_beats, emitter, show_reasoning=show_reasoning
            )
            beats += 1

    # An endpoint that is genuinely down fails EVERY attempt and leaves the turn with nothing
    # to show. That is when the player needs an error rather than a scene which quietly says
    # nothing — not the moment a single generation comes back empty, which is a skipped beat.
    # The silent-turn backstop above has already had its own attempt by this point, so by
    # here "every attempt failed" really does mean the turn has nothing.
    if tally["failures"] and len(tally["failures"]) == tally["attempts"] and not narrated_open:
        raise tally["failures"][-1]

    if beats >= max_beats:  # loop exhausted without an explicit end (runaway backstop)
        yield from tracer.emit(
            "plan",
            "Reached the turn's beat limit",
            detail=f"Stopped after {beats} beats (runaway backstop).",
            data={"end": True},
        )
    if direction.active:
        # Three counts, not two. "Undelivered" used to mean both "no beat ever tried this"
        # and "a beat tried and the prose did not visibly reach it" — and in practice it
        # meant neither, because a requirement was ticked off the moment it entered a
        # prompt. Separating them is the honest report: what landed, what was attempted and
        # could not be confirmed (as likely the lexical check's crudeness as the scene's
        # failure), and what the turn never got to at all.
        unconfirmed = direction.unconfirmed(attempt_cap)
        never = [r for r in direction.outstanding(attempt_cap) if not r.attempted]
        outstanding_total = len(unconfirmed) + len(never)
        delivered_n = len(direction.requirements) - outstanding_total
        yield from tracer.emit(
            "direction",
            (
                "Your direction was delivered in full"
                if not outstanding_total
                else f"{outstanding_total} part(s) of your direction went undelivered"
            ),
            detail=" · ".join(direction.summary()),
            data={
                "delivered": delivered_n,
                "total": len(direction.requirements),
                # Attempted but not confirmed — a beat did aim at these.
                "unconfirmed": [r.text for r in unconfirmed],
                # Never reached at all — the turn ran out of beats first.
                "never": [r.text for r in never],
                # Kept for the client reducer and the existing assertions: everything the
                # turn did not confirm, in the order it was asked for.
                "undelivered": [
                    r.text for r in direction.requirements if not r.delivered
                ],
                # Blocked on someone who is not in the scene — reported separately because
                # "the person you named is not here" is a different problem from "the turn
                # ran out of beats", and only one of them is fixed by a longer scene.
                "blocked": [r.text for r in direction.requirements if r.blocked],
            },
        )

    # A direction outlives the turn it rode in on. Whatever was not delivered is written back
    # to the session so the NEXT turn re-owes it, oldest debt first — including anything
    # blocked on an absent character. This is written even when the direction was fully
    # delivered, because that is what clears a debt the previous turn left.
    if direction.active or session.standing_direction:
        direction_runtime.save_standing(
            db, session, direction_runtime.to_standing(direction, turn=seq0)
        )

    # Nobody produced anything at all (no narration, no character) → a quiet holding
    # narration. A narrator-only open / branch progression already spoke, so skip it then.
    if not acted and not narrated_open and not asked_question:
        yield from emitter.emit(
            "narration", {"text": "The scene waits, quiet.", "done": True}, buffer_role="narrator"
        )

    yield from turn_finalize.finalize_turn(
        db,
        scenario=scenario,
        req=req,
        ctx=ctx,
        session=session,
        seq0=seq0,
        emitter=emitter,
        tracer=tracer,
        turn_beats=turn_beats,
        consequences=consequences,
        pov=pov,
        acted=acted,
        asked_question=asked_question,
        needs_branch=needs_branch,
    )




