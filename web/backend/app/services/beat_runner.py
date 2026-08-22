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




def relationship_note(ctx: TurnContext, speaker_id: str, other_ids: list[str]) -> str:
    """A plain-language summary of how ``speaker`` relates to the others (graph, 2-hop).

    Best-effort → "" when the graph is off / empty (Reactive Turn Director D4)."""
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
    return " ".join(lines[:8])




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
    reaches in their own words, never lines to recite (Narrator-Guided Scenes)."""
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


