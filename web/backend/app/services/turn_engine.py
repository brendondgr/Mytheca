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
    # Per-scene hard ceiling on the beats a single player message produces (Scene Dialogue
    # Updates). The planner may still end the turn earlier; this only caps a drawn-out
    # exchange. The ceiling counts EVERY emitted beat — character replies AND narrator beats
    # (request #3) — so a hard cap of N is never exceeded: the scene-setting narrated open
    # and any puppet performances count toward it, as does each mid-turn interstitial.
    # Resolved here (rather than beside the loop) because the opening narration below has to
    # know how much of the direction it must absorb.
    max_turns = max(1, scenario.max_turns)
    # A direction asking for more than the scene has beats cannot be spread one per beat, so
    # an opening narration absorbs EVERY narrator-owned line at once rather than letting some
    # fall off the end of the turn. With room to spare it takes just the first, and the rest
    # pace out across the loop.
    open_limit = None if max_turns <= len(direction.requirements) else 1
    if outcome:
        yield from tracer.emit(
            "plan", "The narrator plays out your choice", detail=outcome, data={"outcome": outcome}
        )
        owed = direction.for_actor(None)[:open_limit]
        narrated_open = yield from beat_runner.narrator_interstitial(
            db, ctx, turn_beats, emitter, show_reasoning=show_reasoning,
            lead=direction_runtime.direction_lead(direction, owed, base=outcome), long=True,
        )
        if narrated_open:
            yield from direction_runtime.delivered(tracer, ctx, direction, owed)
    elif scene_opening and not intent.directed_actors and not intent.addressed and intent.scope != "all":
        yield from tracer.emit(
            "plan",
            "The narrator opens the scene",
            detail="Scene start — the narrator sets the moment before anyone responds.",
        )
        owed = direction.for_actor(None)[:open_limit]
        narrated_open = yield from beat_runner.narrator_interstitial(
            db, ctx, turn_beats, emitter, show_reasoning=show_reasoning,
            lead=direction_runtime.direction_lead(direction, owed, base="Open the scene."), long=True,
        )
        if narrated_open:
            yield from direction_runtime.delivered(tracer, ctx, direction, owed)

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
        owed = direction.for_actor(speaker.id)
        yield from direction_runtime.delivered(tracer, ctx, direction, owed, by=speaker.id)
        yield from beat_runner.generate_speaker(
            db, ctx, speaker, emitter, turn_beats, consequences,
            show_reasoning=show_reasoning, directive=intent.directive, relationship_note=note,
            direction=direction, requirements=owed, tracer=tracer,
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
        outstanding = direction.outstanding()
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
            yield from direction_runtime.delivered(tracer, ctx, direction, owed, by=scheduled.actor_id)
            forced_actor = ctx.cast_by_id(scheduled.actor_id) if scheduled.actor_id else None
            if forced_actor is None:
                yield from tracer.emit(
                    "direction",
                    "The narrator delivers your direction",
                    detail=forced_reason,
                    data={"requirements": [r.text for r in owed]},
                )
                yield from beat_runner.narrator_interstitial(
                    db, ctx, turn_beats, emitter, show_reasoning=show_reasoning,
                    lead=direction_runtime.direction_lead(direction, owed),
                    # Several requirements bundled into one closing beat need a paragraph,
                    # not a two-sentence transition, to actually land them all.
                    long=len(owed) > 1,
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
                played = yield from beat_runner.beat_or_skip(
                    tracer, forced_actor, tally,
                    db=db, ctx=ctx, emitter=emitter, turn_beats=turn_beats,
                    consequences=consequences,
                    show_reasoning=show_reasoning, relationship_note=note,
                    direction=direction, requirements=owed,
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
            owed = direction.for_actor(None)[:1]
            yield from direction_runtime.delivered(tracer, ctx, direction, owed)
            yield from beat_runner.narrator_interstitial(
                db, ctx, turn_beats, emitter, show_reasoning=show_reasoning,
                lead=direction_runtime.direction_lead(direction, owed) or None,
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
        owed = direction.for_actor(actor.id)[:1]
        yield from direction_runtime.delivered(tracer, ctx, direction, owed, by=actor.id)
        played = yield from beat_runner.beat_or_skip(
            tracer, actor, tally,
            db=db, ctx=ctx, emitter=emitter, turn_beats=turn_beats,
            consequences=consequences,
            show_reasoning=show_reasoning, relationship_note=note,
            register=decision.register, stakes=decision.stakes,
            direction=direction, requirements=owed,
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
        undelivered = direction.outstanding()
        yield from tracer.emit(
            "direction",
            (
                "Your direction was delivered in full"
                if not undelivered
                else f"{len(undelivered)} part(s) of your direction went undelivered"
            ),
            detail=" · ".join(direction.summary()),
            data={
                "delivered": len(direction.requirements) - len(undelivered),
                "total": len(direction.requirements),
                "undelivered": [r.text for r in undelivered],
            },
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




