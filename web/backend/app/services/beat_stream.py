"""Beat streaming — turning one model emission into delta-streamed story events.

Split out of ``beat_runner`` (the owner's structural call, 2026-08-21) so that *producing* a
beat and *transmitting* it are separate concerns. This module owns the wire behaviour:
parse the emission as it arrives, hold a passage's opening until it has been judged, emit
incremental ``text`` under one event id, and enforce the hard per-beat stops.

The two stops are deliberately different things. :data:`_DEGENERATE_AFTER_CHARS` catches a
*collapsed* generation (a loop); :func:`runaway_chars` is an absolute ceiling derived from
the beat-length tier, because ``max_tokens`` alone does not bound prose — thinking and
answer share that budget, so a beat that deliberates briefly can spend the rest writing.

Depends on ``turn_effects`` (a streamed emission may declare consequences); depended on by
``beat_runner``.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy.orm import Session

from app.agents import character_turn_agent
from app.events.envelope import StoryEvent
from app.events.stream import TurnReasoningFrame, TurnTraceFrame
from app.services import emission
from app.services.assembler import CastMember, TurnContext
from app.services.turn_effects import (
    apply_declared_presence,
    apply_relationship_change,
    apply_stat_change,
)
from app.services.turn_emit import Emitter, LiveSegment, Tracer
from app.services.turn_writer import Consequence


#: ONE passage (``emission`` — one beat is one passage), which is what makes the loop
#: visible in a single body instead of arriving as several plausible-looking beats.
_DEGENERATE_AFTER_CHARS = 2000

#: Hard stop on a single beat, whatever it is writing — the passage allowance expressed in
#: characters, so the two cannot drift apart.
#:
#: ``max_tokens`` alone does not bound the prose, because thinking and answer share it: the
#: scratchpad's headroom is fungible, and a beat that deliberates briefly can spend the rest
#: on writing. A verification run produced an 11,998-character beat that way, well inside its
#: token budget. Long beats then feed on themselves — the transcript carries them into the
#: next prompt and the next beat imitates their length (prompt tokens went 1,069 -> 11,606
#: across five turns in that run).
#:
#: It is also what protects the endpoint. An earlier run produced ONE generation of 48,000
#: completion tokens over 684 seconds; the relay's health probe timed out three times against
#: the busy upstream, marked the endpoint failed, and every turn after that came back 400.
#: One beat cost the player the rest of the scene. Neither quality guard could see it — the
#: runaway was well-formed, non-repeating prose the whole way.
#:
#: This is not an editorial limit. Nothing in the contract tells a character to be brief, and
#: with the sampler fixed (EXP-2026-08-007) a passage averages 674 characters with a measured
#: worst case of 1,923 — so the stop sits about four times past the worst honest beat and
#: will not be reached by writing.
#: Per ``beat_length`` tier, because the allowance is: a `short` beat that ignores its
#: directive must not be allowed to stream a `long` one's worth of prose. Derived from
#: ``character_turn_agent.prose_tokens_for`` rather than chosen here — two independently
#: picked limits for the same thing is how one of them ends up wrong.
_CHARS_PER_TOKEN = 4


def runaway_chars(beat_length: str | None) -> int:
    """The hard stop for this beat, in characters."""
    tokens = character_turn_agent.prose_tokens_for(beat_length) or 2048
    return tokens * _CHARS_PER_TOKEN



def stream_emission(
    db: Session,
    ctx: TurnContext,
    speaker: CastMember,
    emitter: Emitter,
    turn_beats: list[dict],
    consequences: list[Consequence],
    *,
    roster: dict[int, str],
    directive: str | None,
    relationship_note: str | None,
    register: str | None,
    stakes: str,
    scene_direction: str,
    owed: list[str],
    tracer: Tracer,
    show_reasoning: bool = False,
    usage_out: dict | None = None,
    replace: dict[str, tuple[str, int]] | None = None,
): 
    """Drive one character generation as a stream; return ``(raw, prompt_tokens, impact, blocked)``.

    Each segment is emitted, appended to ``turn_beats`` and traced the moment the parser
    recognises it — so the character's private thought completes while their spoken line
    is still being written, which is the whole point of the exercise. Every beat takes
    this path: the continuity guard that used to make a later beat hold its prose for a
    verdict is gone, so nothing waits on a complete line any more.

    ``blocked`` says the passage was withheld because it was the model briefing itself
    rather than a character speaking (see :func:`emission.looks_like_scratchpad`). Nothing
    was shown or persisted, so the caller may simply try again.
    """
    stream = character_turn_agent.stream_line(
        db, ctx, speaker, turn_beats=turn_beats, directive=directive,
        relationship_note=relationship_note, register=register, stakes=stakes,
        scene_direction=scene_direction, requirements=owed, usage_out=usage_out,
    )
    acc = emission.EmissionAccumulator(roster=roster, fallback_speaker_id=speaker.id)
    open_segments: dict[int, LiveSegment] = {}
    buffered: dict[int, str] = {}
    impact = 0
    # Everyone else in the scene, for the cross-speaker check below. Empty (a solo scene)
    # skips the check entirely rather than scanning for nobody.
    others_present = [m.name for m in ctx.cast if m.id != speaker.id and m.is_present]
    # Which segment index holds the passage. `open_segments` is keyed by index and carries
    # thoughts and JSON blocks too; only the prose may be cut.
    acc_types: dict[int, str] = {}

    # A passage is never length-capped: a character may hold the floor for as long as the
    # moment needs, and it streams, so length costs the reader nothing. What IS bounded is a
    # generation that has stopped producing language — live runs produced 29,660 and 48,167
    # character beats that opened as prose, drifted into the model's own notes and ended in
    # "Rex Rex Rex" / "AT AT AT AAAA". Watching the tail lets the ceiling stay off.
    written = 0
    degenerate = False
    # The passage's OPENING is held back rather than streamed on arrival. Two live beats
    # were persisted and rendered as a character's prose while being the model briefing
    # itself — the output contract read back ("then main passage then optional structured
    # blocks each opening tag own line JSON…"), and third-person planning about the
    # character it was supposed to BE. Both are well-formed language, so the degeneration
    # guard passes them; the only way to keep them off the page is to look before showing
    # anything. A few hundred characters of delay, against a first-word latency measured in
    # seconds, is a trade worth making. Only the passage is gated — a private thought is
    # machinery the reader has already opted into seeing.
    held: list[emission.SegmentDelta] = []
    held_text = ""
    gate_open = False
    scratchpad = False
    # Sized to THIS scene's beat length, so a `short` beat that ignores its directive is
    # stopped at a short beat's ceiling rather than a long one's.
    runaway_limit = runaway_chars(getattr(ctx, "beat_length", None))

    def _pass(seg: emission.SegmentDelta) -> Generator[Any, None, int]:
        """Emit one parsed delta, holding the passage's opening until it has been judged."""
        nonlocal held, held_text, gate_open, scratchpad
        if scratchpad or seg.type != emission.PROSE_TYPE or gate_open:
            if scratchpad and seg.type == emission.PROSE_TYPE:
                return 0  # the withheld passage never becomes an event
            return (
                yield from emit_segment_delta(
                    db, ctx, speaker, emitter, turn_beats, consequences,
                    seg, open_segments, buffered, tracer, replace,
                )
            )
        held.append(seg)
        held_text += seg.text
        # A passage that opens on a lowercase letter never started — it is the tail of
        # something the model was saying to itself, and it is judged on the first word
        # rather than on the window, because the early release below would let it through
        # (the observed fragment said "my", so the first-person test exempted it).
        if emission.starts_mid_sentence(held_text):
            scratchpad = True
            held = []
            return 0
        # "The player's question feels like a stone dropped into a well" — the transcript's
        # label for the human, used as a name for a person in the room. Judged here rather
        # than after the early release below, because these passages are full of first-person
        # pronouns and would sail through it. The real fix is the label (`You:`) and the
        # contract rule; this only catches an opening, which is all the gate can see.
        if emission.names_the_player(held_text, window=emission.SCRATCHPAD_WINDOW):
            scratchpad = True
            held = []
            return 0
        # Under Playwright mode nobody in the scene can address the player — they are not in
        # the room. A baseline smoke run had 9 of 10 beats doing it anyway, with the narrator
        # writing "he reaches out to grab your wrist". Judged in the same place and the same
        # way as the check above: on the opening only, because that is all the gate holds,
        # and never under POV, where a second person aimed at the player is correct.
        if not ctx.player_embodied and emission.addresses_the_reader(
            held_text, window=emission.SCRATCHPAD_WINDOW
        ):
            scratchpad = True
            held = []
            return 0
        # Release the moment the passage proves itself — a first-person pronoun is what a
        # leaked scratchpad never has, and most passages clear it inside their first
        # sentence. Without this early exit the hold would turn every short beat into a
        # lump that arrives whole at the end of the stream.
        if not emission.in_the_scene(held_text):
            # Otherwise judge once there is enough to judge — or at the end of a passage
            # shorter than the window, which must still be released rather than stranded.
            if not seg.done and len(held_text) < emission.SCRATCHPAD_WINDOW:
                return 0
        if emission.looks_like_scratchpad(held_text) or echoes_a_beat(held_text, turn_beats):
            scratchpad = True
            held = []
            return 0
        gate_open = True
        pending, held = held, []
        total = 0
        for delta in pending:
            total += yield from emit_segment_delta(
                db, ctx, speaker, emitter, turn_beats, consequences,
                delta, open_segments, buffered, tracer, replace,
            )
        return total

    try:
        while True:
            delta = next(stream)
            if delta.reasoning and show_reasoning:
                # Ephemeral: the model's scratchpad, streamed live and never persisted.
                # Kept out of the story record deliberately — it is machinery, not prose.
                yield TurnReasoningFrame(character_id=speaker.id, text=delta.reasoning)
            if not delta.answer:
                continue
            written += len(delta.answer)
            for seg in acc.push(delta.answer):
                acc_types[seg.index] = seg.type
                impact += yield from _pass(seg)
            if scratchpad:
                stream.close()
                break
            # One beat, one speaker. The contract has forbidden writing another character's
            # words since before any of the prose experiments and nothing ever checked it —
            # this is the owner's "Zoe starts talking during Lily's beat", and a live smoke
            # run reproduced it in paragraph four of an otherwise clean passage.
            #
            # Checked on the WHOLE passage as it grows, not on the opening the scratchpad
            # gate holds: a leak is what happens when a beat runs on past its own end, so the
            # opening is precisely where it never is.
            #
            # Cut rather than discarded. Three good paragraphs should not be regenerated for
            # the sake of a fourth, and the point of the guard is that the *scene* never
            # conditions on the intrusion — which trimming what gets persisted achieves.
            if others_present:
                prose_seg = next(
                    (
                        live
                        for idx, live in open_segments.items()
                        if acc_types.get(idx) == emission.PROSE_TYPE
                    ),
                    None,
                )
                found = (
                    emission.cross_speaker_speech_span(prose_seg.text, others=others_present)
                    if prose_seg is not None
                    else None
                )
                if found:
                    leaked_name, at = found
                    prose_seg.truncate(emission.cut_before(prose_seg.text, at))
                    stream.close()
                    yield from tracer.emit(
                        "prose",
                        f"{speaker.name}'s beat was cut where {leaked_name} started talking",
                        detail=(
                            f"The passage gave {leaked_name} a spoken line inside "
                            f"{speaker.name}'s own beat. It was cut back to before that, so "
                            "the scene does not carry it forward as something that was said."
                        ),
                        data={
                            "characterId": speaker.id,
                            "crossSpeaker": leaked_name,
                        },
                    )
                    break
            # The hard stop comes first: it is the one that protects the endpoint, and it
            # must not depend on a quality judgement that a well-formed runaway passes.
            if written > runaway_limit:
                degenerate = True
                stream.close()
                break
            # Only worth checking once the beat is longer than any ordinary one, so a
            # short repetitive line — which people do write — is never mistaken for it.
            if written > _DEGENERATE_AFTER_CHARS:
                open_text = "".join(
                    live.text for live in open_segments.values()
                ) or acc.segments[-1].text if acc.segments else ""
                if emission.looks_degenerate(open_text) or emission.repeats_itself(open_text):
                    degenerate = True
                    stream.close()
                    break
    except StopIteration as stop:
        raw, prompt_tokens = stop.value
    if degenerate:
        raw, prompt_tokens = "", None
        yield from tracer.emit(
            "prose",
            f"{speaker.name}'s beat was cut short",
            detail=(
                "The generation stopped producing language, began writing the same passage "
                "again, or ran past the point where any beat ends, and was cut rather than "
                "streamed further. The beat keeps what it had written."
            ),
            data={"characterId": speaker.id, "degenerate": True},
        )

    # The beat's prose lands before the reasoning display is told to clear. A short passage
    # with no first-person pronoun in it ("Hm.") is held by the scratchpad gate until here,
    # and the reader should not watch the deliberation vanish and then wait for the words.
    for seg in acc.finish():
        impact += yield from _pass(seg)
    if show_reasoning:
        yield TurnReasoningFrame(character_id=speaker.id, done=True)
    if scratchpad:
        raw, prompt_tokens = "", None
    # A stream that ended mid-segment (a truncated completion) must not leave an event
    # open and unpersisted.
    for live_seg in open_segments.values():
        yield from live_seg.close()
    open_segments.clear()
    return raw, prompt_tokens, impact, scratchpad


def emit_segment_delta(
    db: Session,
    ctx: TurnContext,
    speaker: CastMember,
    emitter: Emitter,
    turn_beats: list[dict],
    consequences: list[Consequence],
    seg: emission.SegmentDelta,
    open_segments: dict[int, LiveSegment],
    buffered: dict[int, str],
    tracer: Tracer,
    replace: dict[str, tuple[str, int]] | None = None,
) -> Generator[StoryEvent | TurnTraceFrame, None, int]:
    """Route one parsed increment to the wire; return the stat impact it carried.

    Prose that reads well arriving piecemeal (``character_prose``, and the older
    ``internal_thought`` / ``character_dialogue``) delta-streams. ``character_action`` is
    held and sent whole: it is one short beat, and the client folds it into the speaker's
    open bubble — a rule that only works while the bubble has no spoken text yet. The JSON
    types are held because half an object is not parseable, and are applied through the
    same handlers the batch path uses.
    """
    if seg.type in ("character_prose", "internal_thought", "character_dialogue"):
        live_seg = open_segments.get(seg.index)
        if live_seg is None:
            live_seg = emitter.open_stream(
                seg.type,
                character_id=seg.character_id,
                visibility="private_to_user" if seg.type == "internal_thought" else None,
                buffer_role=None if seg.type == "internal_thought" else "character",
                # A re-roll streams each part back into the row it is replacing, keyed by
                # type. The accompanying thought is replaced too, not appended: the old one
                # explained the line that no longer exists, and leaving it would stack a
                # fresh thought beside a stale one on every re-roll.
                replace=(replace or {}).get(seg.type),
            )
            open_segments[seg.index] = live_seg
        if seg.text:
            yield from live_seg.delta(seg.text)
        if seg.done:
            text = live_seg.text
            yield from live_seg.close()
            open_segments.pop(seg.index, None)
            if seg.type == "internal_thought":
                # Kept OUT of turn_beats: it is the character's interiority, not shared
                # dialogue, and later speakers must never condition on it. Only the older
                # three-fragment shape produces this; a ``character_prose`` beat carries
                # its interiority in the passage the next speaker reads (see below).
                yield from tracer.emit(
                    "thinking", f"{speaker.name} thinks (private)",
                    detail=text, data={"characterId": seg.character_id},
                )
            else:
                # A prose beat goes into turn_beats whole — including the interiority
                # woven through it. That is a deliberate consequence of the single-passage
                # form: the next speaker reads the passage as written, the way a reader
                # does, rather than a stripped-down "spoken line only" version of it.
                turn_beats.append(
                    {"role": "character", "text": text, "characterId": seg.character_id}
                )
                yield from tracer.emit(
                    "dialogue" if seg.type == "character_dialogue" else "prose",
                    f"{speaker.name} speaks",
                    detail=text, data={"characterId": seg.character_id},
                )
        return 0

    # Held types: accumulate, act on close.
    buffered[seg.index] = buffered.get(seg.index, "") + seg.text
    if not seg.done:
        return 0
    body = buffered.pop(seg.index, "")
    if not body:
        return 0
    if seg.type == "character_action":
        yield from emitter.emit(
            "character_action",
            {"characterId": seg.character_id, "text": body},
            buffer_role="character",
            character_id=seg.character_id,
        )
        turn_beats.append({"role": "character", "text": body, "characterId": seg.character_id})
        yield from tracer.emit(
            "action", f"{speaker.name} acts", detail=body, data={"characterId": seg.character_id}
        )
        return 0
    # A re-roll rewrites one beat's WORDING; it must not re-apply its consequences. The
    # original beat's stat, relationship and presence changes already happened and are
    # recorded — applying the new take's as well would drift a character's stats a little
    # further every time the player asked for a different line, and stack a fresh
    # `state_update` row onto the end of the scene each time.
    if replace is not None:
        if seg.type in ("state_update", "relationship_update", "presence_change"):
            yield from tracer.emit(
                seg.type,
                "Consequence skipped on a re-roll",
                detail="A re-take changes the wording, not the world.",
                data={"characterId": seg.character_id},
            )
            return 0
    if seg.type == "state_update":
        return (
            yield from apply_stat_change(
                db, ctx, seg.character_id, body, emitter, consequences, tracer=tracer
            )
        )
    if seg.type == "relationship_update":
        yield from apply_relationship_change(ctx, seg.character_id, body, consequences, tracer)
        return 0
    if seg.type == "presence_change":
        yield from apply_declared_presence(ctx, seg.character_id, body, emitter, tracer)
    return 0


#: How much of two beats' openings have to match before one is called an echo of the other.
#: Long enough that a shared first clause ("The rain has not stopped") is not an echo, short
#: enough to catch the case that matters — a whole passage repeated in someone else's mouth.

_ECHO_PREFIX = 120


def echoes_a_beat(opening: str, turn_beats: list[dict]) -> bool:
    """True when this passage is starting the same way one already played this turn.

    Two characters returning byte-identical passages is not a parser fault — it is two
    separate calls whose prompts differ only by a name and a role, which is what happens
    when a cast has no traits, voice samples or stats to tell them apart. It was visible in
    the owner's own export (Valdar's beat restating Fennel's imagery) and in a live run
    (three pairs of byte-identical beats attributed to different characters, one pair
    fourteen seconds apart).

    Checked on the opening because that is all the gate is holding, and regenerating costs
    one call — the same machinery a leaked scratchpad already uses.
    """
    head = (opening or "").strip()[:_ECHO_PREFIX]
    if len(head) < _ECHO_PREFIX:
        return False
    return any(
        (beat.get("text") or "").strip().startswith(head)
        for beat in turn_beats
        if beat.get("role") == "character"
    )


