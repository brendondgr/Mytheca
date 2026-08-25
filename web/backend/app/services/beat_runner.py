"""Beat generation — producing one already-decided beat.

``turn_engine`` decides *who* speaks next and *why*; this module produces that beat. It is
the narrowest of the turn modules on purpose (the owner's structural call, 2026-08-21):

* :func:`generate_speaker` / :func:`beat_or_skip` — one character's passage, in their own
  voice, against the outcomes the direction owes them.
* :func:`narrator_interstitial` — the narrator's own beat between character beats.
* :func:`relationship_note` — the graph context a speaker is given about the others present.

Transmission lives in ``beat_stream``; consequences live in ``turn_effects``.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.agents import narrator_agent
from app.agents.direction_agent import DirectionRequirement, SceneDirection
from app.core.errors import APIError
from app.events.envelope import StoryEvent
from app.events.stream import TurnReasoningFrame, TurnTraceFrame
from app.services import graph_reader
from app.services.assembler import CastMember, TurnContext
from app.services.beat_stream import stream_emission
from app.services.turn_emit import Emitter, Tracer
from app.services.turn_writer import Consequence


def narrator_interstitial(
    db: Session,
    ctx: TurnContext,
    turn_beats: list[dict],
    emitter: Emitter,
    *,
    show_reasoning: bool = False,
    lead: str | None = None,
    long: bool = False,
    replace: dict[str, tuple[str, int]] | None = None,
) -> Generator[StoryEvent | TurnReasoningFrame, None, bool]:
    """Emit an optional narrator beat; skip silently on failure. Returns whether a beat
    was actually emitted (so the caller can tell a real opening from a no-op).

    ``lead``/``long`` drive the fuller opening + branch-progression passage (feedback
    #1/#2/#3); the default (both unset) is the short between-speakers transition beat.

    The prose streams as the model writes it. A scene's first message is narrator-led, so
    this is the very first thing a new player sees — it is the beat that most needs to
    start arriving early rather than landing whole after a long silence."""
    stream = narrator_agent.stream_interstitial(db, ctx, turn_beats, lead=lead, long=long)
    live = emitter.open_stream(
        "narration", buffer_role="narrator", replace=(replace or {}).get("narration")
    )
    try:
        while True:
            delta = next(stream)
            if delta.reasoning and show_reasoning:
                yield TurnReasoningFrame(text=delta.reasoning)
            if delta.answer:
                yield from live.delta(delta.answer)
    except StopIteration as stop:
        text = stop.value
    if not text:
        # Nothing usable — discard the event id rather than persisting an empty beat.
        return False
    yield from live.close()
    turn_beats.append({"role": "narrator", "text": live.text, "characterId": None})
    return True




#: How much of a speaker's history reaches their beat. Mirrors ``schemas.play.TieScope``.
#:
#: ``"addressed"`` is what shipped before this control: the caller's own ``other_ids``, which
#: the planner narrows to just the addressee. ``"scene"`` — the default — is the same query
#: with a wider id list, so it costs nothing new and gives a speaker the room rather than one
#: person. ``"world"`` adds ``graph_reader.offscene_ties``, the only new query in the feature.
_TIE_SCOPES = ("addressed", "scene", "world")

#: How many relationship lines a speaker is given, and how many of those the `world` stop may
#: reserve for people outside the scene. The total is the prompt budget; the reservation is
#: what stops a dense in-scene graph from silently crowding the off-scene ties out entirely.
_NOTE_LINES = 8
_NOTE_ELSEWHERE = 2


def relationship_note(
    ctx: TurnContext,
    speaker_id: str,
    other_ids: list[str],
    *,
    scope: str = "scene",
) -> str:
    """A plain-language summary of how ``speaker`` relates to the others (graph, 2-hop).

    ``scope`` decides who counts (see :data:`_TIE_SCOPES`). At ``"scene"`` and ``"world"`` the
    id list is every other **present** cast member rather than the caller's — a speaker
    carrying only the addressee's history is why two characters could stand in the same room
    with a decade between them and neither mention it.

    Best-effort → "" when the graph is off / empty (Reactive Turn Director D4)."""
    if scope not in _TIE_SCOPES:
        scope = "scene"
    if scope in ("scene", "world"):
        other_ids = [m.id for m in ctx.cast if m.is_present and m.id != speaker_id]
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
    if scope != "world":
        return " ".join(lines[:_NOTE_LINES])

    # Marked as elsewhere, deliberately: without the clause a speaker reads these as people
    # in the room and answers them.
    elsewhere: list[str] = []
    for tie in graph_reader.offscene_ties(
        speaker_id,
        [m.id for m in ctx.cast],
        getattr(ctx, "storyline_id", "") or "",
    ):
        verb = str(tie.get("type", "")).replace("_", " ")
        reason = f" ({tie['reason']})" if tie.get("reason") else ""
        if tie.get("outgoing"):
            elsewhere.append(f"Elsewhere: you {verb} {tie['name']}{reason}, who is not in this scene.")
        else:
            elsewhere.append(f"Elsewhere: {tie['name']} {verb} you{reason}, and is not in this scene.")

    # Off-scene ties get a RESERVED share of the budget rather than the leftovers.
    #
    # Appending them and trimming to 8 was the obvious thing and it is wrong: a live check
    # against a world with a dense in-scene graph produced eight in-scene lines and the
    # elsewhere clause was cut every time, so the `world` stop did nothing at all — silently,
    # and precisely on the worlds rich enough to want it. The total is still capped at
    # `_NOTE_LINES`; what changes is that the room can no longer crowd the world out entirely.
    reserved = min(len(elsewhere), _NOTE_ELSEWHERE)
    return " ".join(lines[: _NOTE_LINES - reserved] + elsewhere[:reserved])




def relationship_step(
    tracer: "Tracer", name: str, character_id: str, note: str, scope: str
) -> Generator[TurnTraceFrame, None, None]:
    """Trace one speaker's ties, if there are any.

    Lives beside :func:`relationship_note` rather than in the beat loop because it describes
    that function's output, and the loop was carrying two byte-identical copies of it.
    """
    if not note:
        return
    yield from tracer.emit(
        "relationship",
        f"{name}'s ties",
        detail=note,
        data={
            "characterId": character_id,
            "scope": scope,
            # How many lines describe someone who is NOT in the room. Only the `world` stop
            # can produce them, and a player who turned it on should be able to see whether
            # it did anything.
            "offscene": note.count("Elsewhere:"),
        },
    )


def continuous_turn(
    db: Session,
    ctx: TurnContext,
    planned: list,
    emitter: Emitter,
    turn_beats: list[dict],
    consequences: list[Consequence],
    intent,
    direction,
    *,
    enabled: bool,
    tracer: Tracer,
    pov_id: str | None,
    show_reasoning: bool,
    lookahead: int,
    scene_opening: bool,
) -> Generator[StoryEvent | TurnReasoningFrame | TurnTraceFrame, None, bool]:
    """Write the whole turn as ONE continuous script. Returns whether it played.

    ``sceneFlow: "continuous"``. The plan is produced once (or taken from an approved one),
    then a single generation writes every beat of it, marking each change of speaker with
    ``<speaker:N>``. Each hand-off opens its own event with its own ``characterId``, so the
    client's speaker-change signal is the ordinary event boundary and no new contract exists.

    **Returns False rather than raising when it cannot do the job**, and the caller then runs
    the ordinary per-speaker loop for that turn. Two ways that happens, and both matter:

    * The plan has nothing in it to write. Nothing was generated, so nothing is wasted.
    * The model ignored the token format and returned one long passage
      (``scene_script_agent.looks_unscripted``). That parses as a single beat attributed to
      whoever was first — a mis-attributed monologue, which is worse than what the voiced
      path would have produced. This is the case the owner's "foolproof on less intelligent
      models" asks for, and the degradation has to be to today's behaviour, never to
      something worse.
    """
    from app.agents import character_turn_agent, planner_agent, scene_script_agent
    from app.services.beat_stream import stream_script

    # The mode check lives here rather than at the call site so the engine reads as one line
    # and `run_turn` stays under the module's line ceiling — which is what the ceiling is for.
    if not enabled:
        return False
    present = [m for m in ctx.cast if m.is_present and m.id != pov_id]
    if not present:
        return False
    roster = {i + 1: m.id for i, m in enumerate(present)}
    if not planned:
        planned = planner_agent.plan_beats(
            db, ctx, intent, turn_beats, [], lookahead=max(lookahead, 4),
            scene_opening=scene_opening, locked_id=pov_id,
            direction=direction if direction and direction.active else None,
        )
    writable = [d for d in planned if d.action in ("speak", "narrate")]
    if not writable:
        return False

    speakers = len({d.actor_id for d in writable if d.actor_id})
    yield from tracer.emit(
        "prose",
        f"Writing the scene in one pass ({len(writable)} beat(s))",
        detail=(
            "Continuous scene flow: one generation writes every beat of the plan and marks "
            "each change of speaker, instead of one call per speaker."
        ),
        data={"sceneFlow": "continuous", "beats": len(writable), "speakers": speakers},
    )
    owed = [r.text for r in (direction.outstanding() if direction else [])]
    mark = len(turn_beats)
    raw, _tokens, _impact, _blocked = yield from stream_script(
        db, ctx, writable, emitter, turn_beats, consequences,
        roster=roster,
        transcript=character_turn_agent._transcript(ctx, turn_beats),
        scene_direction=getattr(direction, "text", "") or "",
        owed=owed, tracer=tracer, show_reasoning=show_reasoning,
    )
    if scene_script_agent.looks_unscripted(raw, expected_speakers=speakers):
        yield from tracer.emit(
            "prose",
            "The scene came back unscripted — writing it per speaker instead",
            detail=(
                "The model produced one passage with no speaker hand-offs at all, which would "
                "have been attributed to a single character. This turn falls back to one call "
                "per speaker."
            ),
            data={"sceneFlow": "fallback"},
        )
        # Anything the script did emit is dropped from the turn's own transcript so the
        # per-speaker path does not react to a beat the reader is about to see re-written.
        del turn_beats[mark:]
        return False
    return len(turn_beats) > mark


def beat_or_skip(
    tracer: "Tracer",
    speaker: CastMember,
    tally: dict,
    **kwargs,
) -> Generator[StoryEvent | TurnTraceFrame, None, bool]:
    """Run one beat; return whether it played. A failure is traced and skipped, never fatal.

    A single call can come back with nothing in it — most often "the model spent its whole
    budget thinking and never answered", which happens when the deliberation runs past its
    (advisory) budget. Left alone that raises out of the beat loop as a terminal error frame
    and takes the whole turn with it: one live run lost a turn that had already streamed
    three beats, and another lost one to its very first beat.

    The failure is recorded in ``tally`` rather than swallowed. Whether it reaches the player
    is decided at the END of the turn, by whether EVERY attempt failed — a one-off starved
    generation is a skipped beat, and an endpoint that is genuinely down fails all of them,
    shows nothing, and surfaces as an error. That is a better test than guessing at the
    moment it happens, and it is why the attempts are counted and not just the failures.
    """
    tally["attempts"] += 1
    try:
        yield from generate_speaker(speaker=speaker, tracer=tracer, **kwargs)
        return True
    except APIError as exc:
        tally["failures"].append(exc)
        yield from tracer.emit(
            "prose",
            f"{speaker.name}'s beat did not come back",
            detail=f"{exc.message} The turn carries on with what it has.",
            data={"characterId": speaker.id, "skipped": True},
        )
        return False


def generate_speaker(
    db: Session,
    ctx: TurnContext,
    speaker: CastMember,
    emitter: Emitter,
    turn_beats: list[dict],
    consequences: list[Consequence],
    *,
    show_reasoning: bool = False,
    directive: str | None = None,
    relationship_note: str | None = None,
    register: str | None = None,
    stakes: str = "",
    direction: SceneDirection | None = None,
    requirements: list[DirectionRequirement] | None = None,
    tracer: Tracer | None = None,
    replace: dict[str, tuple[str, int]] | None = None,
) -> Generator[StoryEvent | TurnTraceFrame, None, int]:
    """Generate one speaker's beat, emit its events as they arrive, append them to
    ``turn_beats``, and return the beat's impact (Σ|stat delta|) for the live queue.

    ``register``/``stakes`` are the planner's read of this beat's moment (see
    ``planner_agent.BeatDecision``); they reach the character prompt's recency tail so the
    speaker performs against a stated situation instead of inferring one. A puppet beat runs
    before the planner has decided anything — and a forced direction beat runs *instead* of
    asking it — so both carry no register and the prompt falls back to its generic "read the
    moment" cue.

    ``directive`` marks a **puppet** beat (the player directed this character): the
    character performs it in-voice and the continuity guard is skipped (there is nothing
    to contradict — the player asked for it). ``relationship_note`` folds the speaker's
    graph relationships (to whom they address, + 2-hop) into the prompt (D4).

    ``direction`` is where the player is steering the whole scene (context every speaker
    plays toward) and ``requirements`` are the parts THIS beat owes — outcomes the character
    reaches in their own words, never lines to recite (Playwright-guided scenes)."""
    tr = tracer or Tracer(False)
    roster = {i + 1: m.id for i, m in enumerate(ctx.cast)}
    scene_direction = direction.text.strip() if direction is not None else ""
    owed = [r.text for r in requirements or []]
    # Filled by the transport with this call's token figures. ``cached_tokens`` is how
    # much of the prompt the server reused from its KV cache rather than re-reading — the
    # only signal that catches a prompt-cache regression before it shows up as latency
    # that creeps upward as a scene gets longer.
    usage: dict = {}
    _raw, prompt_tokens, streamed_impact, blocked = yield from stream_emission(
        db, ctx, speaker, emitter, turn_beats, consequences,
        roster=roster, directive=directive, relationship_note=relationship_note,
        register=register, stakes=stakes, scene_direction=scene_direction, owed=owed,
        tracer=tr, show_reasoning=show_reasoning, usage_out=usage, replace=replace,
    )
    if blocked:
        # The passage was the model briefing itself, and was withheld before the reader saw
        # a word of it — so nothing needs undoing and the speaker simply goes again. Once:
        # a beat that leaks twice is a bad prompt or a bad moment, not bad luck, and the
        # turn is better served moving on than spending a third generation on it. An empty
        # turn is already covered by the silent-turn backstop at the end of the beat loop.
        yield from tr.emit(
            "prose",
            f"{speaker.name} starts again",
            detail=(
                "The first attempt was not this character speaking — notes about the task, "
                "a fragment starting mid-sentence, or the previous beat repeated back — so "
                "it was withheld and the beat regenerated."
            ),
            data={"characterId": speaker.id, "scratchpad": True},
        )
        _raw, prompt_tokens, streamed_impact, blocked = yield from stream_emission(
            db, ctx, speaker, emitter, turn_beats, consequences,
            roster=roster, directive=directive, relationship_note=relationship_note,
            register=register, stakes=stakes, scene_direction=scene_direction, owed=owed,
            tracer=tr, show_reasoning=show_reasoning, usage_out=usage, replace=replace,
        )
        if blocked:
            yield from tr.emit(
                "prose",
                f"{speaker.name}'s beat was dropped",
                detail=(
                    "The second attempt was no better. The beat is skipped rather than "
                    "shown, and the turn carries on."
                ),
                data={"characterId": speaker.id, "scratchpad": True, "dropped": True},
            )

    # Exact context-window usage: the server-reported input-token count for this
    # character call — the real size of everything actually sent (output contract +
    # World Primer + stat guidance + transcript). Streamed live and persisted (the
    # tracer writes it regardless of the opt-in) so the story player's context dial
    # reads the truth, not a char/4 estimate. Omitted when the endpoint reports no
    # usage (the dial then keeps its heuristic fallback).
    reusable = usage.get("reusable_prefix_chars")
    prompt_chars = usage.get("prompt_chars")
    if prompt_tokens is not None or reusable is not None:
        detail = (
            f"{prompt_tokens:,} tokens sent to the model"
            if prompt_tokens is not None
            else "context sent to the model"
        )
        if reusable and prompt_chars:
            detail += f" · {round(100 * reusable / prompt_chars)}% reusable prefix"
        yield from tr.emit(
            "context",
            "Context window",
            detail=detail,
            data={
                "characterId": speaker.id,
                # Omitted (not zeroed) when the endpoint reports nothing, so "no data"
                # stays distinguishable from "nothing was cached".
                **({"promptTokens": prompt_tokens} if prompt_tokens is not None else {}),
                **({"cachedTokens": usage["cached_tokens"]}
                   if usage.get("cached_tokens") is not None else {}),
                # How much of this prompt was byte-identical to the previous character
                # call in this session. Unlike cachedTokens this is computed locally, so
                # it is always present and cannot be hidden by an endpoint that omits its
                # own counter — it is the layout regression alarm.
                **({"reusablePrefixChars": reusable} if reusable is not None else {}),
                **({"promptChars": prompt_chars} if prompt_chars is not None else {}),
            },
        )

    return streamed_impact


