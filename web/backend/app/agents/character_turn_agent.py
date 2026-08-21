"""Character turn agent — voice ONE character for the current beat.

One LLM call per active speaker (per-character isolation — no shared multi-POV
prompt, so voices stay distinct). The model emits **one untagged first-person passage** —
what the character notices, does and says, woven together with the speech in double quotes
inline — optionally followed by a JSON block (``<type:state_update>`` and friends); the
backend owns the envelope (``services.emission``). The prompt is ordered **stable → append-only → volatile** so an
inference server's prefix cache can reuse it across beats and turns: the scene as authored
leads, the transcript follows (append-only, with a block-anchored start), and everything
that changes per beat — this speaker's identity, voice samples, live stat values, the
register, the "respond now" cue — comes last, where recency attention is strongest anyway.
The stable region (output contract + World Primer + stat guidance) rides in the system
message. See ``_build_user_prompt`` for why the ordering is load-bearing.

The character deliberates **in POV, inside the passage** — first person, in their own
voice — rather than in a fenced-off block or a hidden reasoning channel. Both of those
existed once; running both meant thinking the beat through twice and showing only the
second. In-voice sampler tuning is layered on here.
"""

from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy.orm import Session

from app.agents import prompt_registry
from app.agents._common import gen_params, resolve_llm
from app.core.config import get_settings
from app.schemas.reasoning import ReasoningEffort, budget_for
from app.schemas.settings import LlmParams
from app.services import llm
from app.services.assembler import (
    CastMember,
    TurnContext,
    format_voice_samples,
    select_voice_samples,
)
from app.services.stat_render import render_character_stats

logger = logging.getLogger("mytheca.turn")

# The beat needs a place to think that is NOT the prose. Running with the channel off
# entirely (and no <thinking> block either) left deliberation nowhere to go, and a live run
# caught the model writing its own scratchpad into the passage — "need to produce Mei's
# beat. User is player? The cast: [1] Mei…" — before degenerating into a repetition loop at
# 29,660 characters. HIGH caps that channel at 1024 tokens: enough to work the moment out,
# bounded enough that the player is not waiting on an essay nobody reads. The character's
# in-POV deliberation still appears in the passage itself; this is the scratchpad, not the
# interiority.
TURN_EFFORT = ReasoningEffort.HIGH

# Sampler tuning for in-character voice on small models (the turn-loop plan §7):
# repetition/frequency penalties + a lower top_p rein in drift more reliably than
# raising temperature. Applied per turn-call (a per-storyline/character voice setting
# is a recorded seam). Temperature + max_tokens are kept from the operator's config.
_VOICE_TOP_P = 0.92
_VOICE_FREQUENCY_PENALTY = 0.4
_VOICE_PRESENCE_PENALTY = 0.3

# Per-register sampler tuning: (top_p, frequency_penalty, presence_penalty).
#
# Frequency and presence penalties push the model toward tokens it has NOT used yet —
# toward novelty and flourish, which is exactly the quip-seeking behavior that reads as
# a character performing instead of reacting. So they come DOWN as the moment gets
# graver, letting plain, direct, even repetitive language through (people repeat
# themselves when frightened), and up in a light moment where banter should stay varied.
# ``top_p`` narrows alongside them so a grave beat stays on the obvious, sincere word.
#
# A beat with no register (planner fallback, puppet beat, test context) resolves to the
# module defaults above — byte-identical to the pre-register behavior. Temperature and
# max_tokens stay under the operator's config either way.
_REGISTER_SAMPLER = {
    "light": (0.95, 0.45, 0.35),
    "neutral": (0.92, 0.40, 0.30),
    "tense": (0.88, 0.30, 0.20),
    "grave": (0.85, 0.20, 0.15),
}

# Per-register performance directives, stated in the recency TAIL as an established fact
# about the situation rather than a question the speaker has to answer for itself. The
# register comes from ``planner_agent.next_beat`` (which already runs once per beat, so
# this costs no extra LLM call); ``None`` means the planner did not run or replied with
# something unrecognized, and the tail then falls back to the generic "read the moment" cue.
_REGISTER_DIRECTIVES = {
    "light": (
        "The moment is LIGHT — nothing real is on the line right now. Your usual manner "
        "fits here; play it as you would."
    ),
    "neutral": (
        "The moment is ORDINARY — mild friction, nothing at stake yet. Speak plainly as "
        "yourself; don't perform."
    ),
    "tense": (
        "The moment is TENSE — something you care about is genuinely at risk. Let that "
        "show: shorter, sharper, more focused than your habit. Any act you normally keep "
        "up is under strain now."
    ),
    "grave": (
        "The moment is GRAVE — someone is dying, badly hurt, breaking down, or a life is "
        "on the line RIGHT NOW. Your usual manner does NOT fit here. The act drops and the "
        "real person shows: fear, grief, urgency, or tenderness. Do not be witty, do not "
        "be cocky, do not deflect with a joke."
    ),
}

# Default output contract text now lives in ``prompt_registry`` (single source of truth
# for editable writing prompts); resolved per-turn text rides on ``ctx.prompts``.
_OUTPUT_CONTRACT = prompt_registry.default(prompt_registry.CHARACTER_OUTPUT_CONTRACT)


#: Generous ceiling on the PASSAGE — roughly 900 words, several long paragraphs, far more
#: than a character needs to hold the floor through a real moment. This is the prose
#: allowance only; the request budget adds the thinking budget on top (see
#: :func:`_voice_params`).
#:
#: The owner asked for length to be free, and this is a deviation from that, flagged rather
#: than made quietly. Uncapped output was measured twice on the live endpoint and made the
#: writing WORSE, not longer-and-better: beats averaged 8,228 then 10,184 characters
#: (~1,600 words), the shortest was already a drifting run-on with no punctuation and a
#: lowercase "i", and 2 of 5 beats tripped the degeneration guard. Prompt guidance did not
#: bind it — a countable "usually 80-200 words" target moved the average UP. Every beat
#: that read well all session was produced with a ceiling in place.
#:
#: Set this to ``None`` to restore unbounded length; nothing else depends on it.
_VOICE_PROSE_TOKENS = 1200


def _voice_params(
    params: LlmParams,
    register: str | None = None,
    reasoning: ReasoningEffort = TURN_EFFORT,
) -> LlmParams:
    """Bound the beat generously and apply the voice-tuned sampler fields.

    The sampler tracks the beat's ``register`` (see ``_REGISTER_SAMPLER``); an absent or
    unrecognized register keeps the module defaults.

    ``max_tokens`` buys the hidden thinking **and** the answer out of one budget, so the
    passage allowance is added ON TOP of the thinking budget rather than shared with it.
    Capping the request at the passage allowance alone starves the answer: with the two set
    equal at 1,200, a live turn spent the whole budget deliberating and came back as
    reasoning with no prose at all ("the model spent its whole budget thinking and never
    answered"). The cap applies to the ``gen_params`` floor, not to the operator's raw
    ``max_tokens`` — that field defaults to 512, which is a default rather than a choice
    and would starve every beat on a stock install.
    """
    top_p, frequency, presence = _REGISTER_SAMPLER.get(
        register or "", (_VOICE_TOP_P, _VOICE_FREQUENCY_PENALTY, _VOICE_PRESENCE_PENALTY)
    )
    tuned = gen_params(params).model_copy(
        update={
            "top_p": top_p,
            "frequency_penalty": frequency,
            "presence_penalty": presence,
        }
    )
    if not _VOICE_PROSE_TOKENS:
        return tuned
    budget = budget_for(reasoning) + _VOICE_PROSE_TOKENS
    return tuned.model_copy(update={"max_tokens": min(tuned.max_tokens, budget)})


def generate_line(
    db: Session,
    ctx: TurnContext,
    speaker: CastMember,
    *,
    turn_beats: list[dict],
    reasoning: ReasoningEffort = TURN_EFFORT,
    directive: str | None = None,
    relationship_note: str | None = None,
    register: str | None = None,
    stakes: str = "",
    scene_direction: str = "",
    requirements: list[str] | None = None,
) -> str:
    """Generate one character's raw emission for this beat (thin-tag format).

    Thin wrapper over :func:`generate_line_with_usage` that drops the token figure.
    """
    raw, _ = generate_line_with_usage(
        db, ctx, speaker, turn_beats=turn_beats, reasoning=reasoning,
        directive=directive, relationship_note=relationship_note,
        register=register, stakes=stakes,
        scene_direction=scene_direction, requirements=requirements,
    )
    return raw


def generate_line_with_usage(
    db: Session,
    ctx: TurnContext,
    speaker: CastMember,
    *,
    turn_beats: list[dict],
    reasoning: ReasoningEffort = TURN_EFFORT,
    directive: str | None = None,
    relationship_note: str | None = None,
    register: str | None = None,
    stakes: str = "",
    scene_direction: str = "",
    requirements: list[str] | None = None,
) -> tuple[str, int | None]:
    """Generate one character's raw emission + the call's exact ``prompt_tokens``.

    ``prompt_tokens`` (the server-reported input-token count, or ``None`` when the
    endpoint omits ``usage``) is the largest, most representative "context window
    used" figure in a turn — the character call carries the full system prefix
    (output contract + World Primer + stat guidance) plus the transcript — so the
    turn engine surfaces it to the story player's context dial.

    ``turn_beats`` is the chronological this-turn transcript so far (the player's
    line, then any earlier speakers' lines) — so a later speaker genuinely reacts to
    its predecessor (the immediate predecessor sits last, where recency attention is
    strongest). ``directive``
    is a **puppet** performance (Reactive Turn Director D1): the player directed this
    character to do/say something, so the character performs it **in their own voice**
    rather than reacting to the player's words as if spoken to them.

    ``scene_direction`` is where the player is steering the whole scene — context, so even
    an unassigned speaker plays toward it — and ``requirements`` are the outcomes THIS beat
    owes (Narrator-Guided Scenes). Both are guides, not scripts: they say what has to be
    true when the beat ends, and the character reaches it in their own words while every
    in-character constraint above still applies.
    """
    base_url, api_key, model, params = resolve_llm(db)
    contract = ctx.prompts.get(prompt_registry.CHARACTER_OUTPUT_CONTRACT, _OUTPUT_CONTRACT)
    system = f"{contract}\n\n{ctx.stable_prefix}".strip()
    # The system message is byte-identical for every speaker this turn — log its
    # prefix-cache id so warm-prefix reuse across the turn's calls is observable (§P11).
    logger.debug("turn speaker=%s prefix-cache=%s", speaker.id, llm.prefix_cache_key(system))
    user = _build_user_prompt(
        ctx, speaker, turn_beats, directive=directive,
        relationship_note=relationship_note, register=register, stakes=stakes,
        scene_direction=scene_direction, requirements=requirements,
    )
    return llm.chat_complete_usage(
        base_url,
        api_key,
        model,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        _voice_params(params, register, reasoning),
        reasoning=reasoning,
    )


def stream_line(
    db: Session,
    ctx: TurnContext,
    speaker: CastMember,
    *,
    turn_beats: list[dict],
    reasoning: ReasoningEffort = TURN_EFFORT,
    directive: str | None = None,
    relationship_note: str | None = None,
    register: str | None = None,
    stakes: str = "",
    scene_direction: str = "",
    requirements: list[str] | None = None,
    usage_out: dict | None = None,
) -> Generator[llm.StreamDelta, None, tuple[str, int | None]]:
    """Stream one character's emission; return ``(raw_emission, prompt_tokens)``.

    The streaming sibling of :func:`generate_line_with_usage`, taking the same arguments
    and building the identical prompt — the only difference is that the caller sees the
    emission arrive instead of waiting for it. Deltas carry the model's ``reasoning``
    channel separately from the ``answer`` text, so the turn engine can show the
    deliberation without ever mistaking it for prose.

    Falls back to a single whole-emission delta on an endpoint that cannot stream.
    """
    base_url, api_key, model, params = resolve_llm(db)
    contract = ctx.prompts.get(prompt_registry.CHARACTER_OUTPUT_CONTRACT, _OUTPUT_CONTRACT)
    system = f"{contract}\n\n{ctx.stable_prefix}".strip()
    logger.debug("turn speaker=%s prefix-cache=%s", speaker.id, llm.prefix_cache_key(system))
    user = _build_user_prompt(
        ctx, speaker, turn_beats, directive=directive,
        relationship_note=relationship_note, register=register, stakes=stakes,
        scene_direction=scene_direction, requirements=requirements,
    )
    if usage_out is not None:
        # How much of this prompt is byte-identical to the previous character call in this
        # session — the prompt-cache metric the layout actually controls, and the one the
        # endpoint cannot hide from us (vLLM omits its own counter when the hit is zero).
        usage_out["reusable_prefix_chars"] = llm.shared_prefix_chars(
            ctx.session_id, f"{system}\n{user}"
        )
        usage_out["prompt_chars"] = len(system) + len(user) + 1
    return (
        yield from llm.chat_complete_stream(
            base_url,
            api_key,
            model,
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            _voice_params(params, register, reasoning),
            reasoning=reasoning,
            usage_out=usage_out,
        )
    )


def _speaker_number(ctx: TurnContext, speaker: CastMember) -> int:
    for i, member in enumerate(ctx.cast):
        if member.id == speaker.id:
            return i + 1
    return 1


def _build_user_prompt(
    ctx: TurnContext,
    speaker: CastMember,
    turn_beats: list[dict],
    *,
    directive: str | None = None,
    relationship_note: str | None = None,
    register: str | None = None,
    stakes: str = "",
    scene_direction: str = "",
    requirements: list[str] | None = None,
) -> str:
    """Ordered stable → append-only → volatile, so the prompt cache can keep up.

    The prompt is built in three regions, and the ordering is load-bearing rather than
    stylistic. An inference server's prefix cache matches from the **first token** and
    stops at the first byte that differs, so whatever changes earliest decides how much of
    the prompt can be reused:

    * **STABLE** — the setting and the roster. Byte-identical for every speaker and every
      beat of the scene, and it sits behind an equally stable system message (output
      contract + World Primer + stat guidance).
    * **APPEND-ONLY** — the transcript. It only ever grows at the end, and its start is
      held still by ``buffer.anchored_turns``, so turn N+1 matches turn N up to the beats
      that are genuinely new.
    * **VOLATILE** — everything that changes per beat: retrieved lore, the player's tagged
      files, this speaker's identity and voice samples, their live stat values, the beat's
      register, and the act-now cue.

    This replaced a bookended layout (identity first for primacy, transcript in the
    middle). That layout put the speaker's live stat values ahead of the largest reusable
    block in the prompt, which pinned cache reuse to the system message alone —
    EXP-2026-08-005 measured cached tokens at *exactly* 800 on all ten turns of a scene
    while the prompt grew 1830 → 4678, and the reordered arm of its layout probe cut
    time-to-first-token ~40 % at 100+ turns of history.

    Moving identity from primacy to recency is a real change to what the model attends to,
    not a free win: it is the strongest position in the prompt on this model class, but it
    is a different position than the one the voice samples were tuned in. That is a
    writing-quality question, measured alongside the timings rather than assumed.
    """
    number = _speaker_number(ctx, speaker)

    # ---- STABLE — the scene as authored. Identical across speakers and across turns. ----
    stable: list[str] = []
    if ctx.setting is not None:
        # The authored description of the PLACE — written once at world creation and never
        # rewritten during play. It is scenery, not a report of the current mood; the live
        # read of the moment comes from the transcript and the beat's register, not here.
        flavor = ctx.setting.atmosphere or ctx.setting.current_state or ctx.setting.desc or ""
        stable.append(
            f"Where this happens: {ctx.setting.name}{(' — ' + flavor) if flavor else ''} "
            "(the place as authored; how it feels right now is whatever the beats below show)."
            if flavor
            else f"Where this happens: {ctx.setting.name}."
        )
    roster = ", ".join(f"[{i + 1}] {m.name}" for i, m in enumerate(ctx.cast))
    stable.append(f"Cast in the scene: {roster}.")

    # ---- APPEND-ONLY — the transcript, ending on the most recent line. ----
    # Nothing volatile may be inserted above this block: everything below it is re-read by
    # the model on every call, and everything above it is what the cache can keep.
    middle: list[str] = []
    transcript = _transcript(ctx, turn_beats)
    if transcript:
        middle.append(f"Recent beats:\n{transcript}")

    # ---- VOLATILE — changes beat to beat. Ordered context first, instruction last. ----
    tail: list[str] = []
    if ctx.retrieved_lore:
        tail.append(ctx.retrieved_lore.strip())  # fenced reference lore (gated)
    if ctx.tagged_notes:
        # The player's @-tagged files. Deliberately ahead of the direction line below, so
        # the direction keeps the recency advantage: a tagged file informs HOW this
        # character speaks, never WHERE the scene goes.
        tail.append(ctx.tagged_notes.strip())

    tail.append(f"You are [{number}] {speaker.name} — {speaker.role}.")
    if speaker.speech:
        tail.append(f"Speech style (your default voice): {speaker.speech}")
    if speaker.traits:
        tail.append(f"Traits: {speaker.traits}")
    # Concrete situation → sample-response pairs authored for this character — the ground
    # truth for *how* they sound, and the single highest-salience block in this prompt.
    # Selected by the beat's register (untagged pairs always apply, and an unmatched or
    # register-less beat falls back to the whole set) so the exemplars the model imitates
    # are drawn from a moment LIKE this one rather than always from the baseline.
    selected = format_voice_samples(
        select_voice_samples(speaker.voice_sample_rows, register)
    ) or speaker.voice_samples
    if selected:
        if register:
            tail.append(
                f"Voice samples — how you sound in a moment like this one. Keep the person; "
                f"match the pitch of the moment, not a habit:\n{selected}"
            )
        else:
            tail.append(
                "Voice samples — your baseline voice (how you sound at rest; keep the person, but "
                f"let the register flex with the moment):\n{selected}"
            )
    if speaker.stats:
        # Resolve each stat's current band and substitute {Character} with the
        # speaker's name so the model reads what a value *means* for them right now
        # (not a bare k=v). Falls back to the compact k=v when there are no defs.
        state = render_character_stats(ctx.stat_defs, speaker.stats, speaker.name)
        if state:
            tail.append(state)
        else:
            flat = ", ".join(f"{k}={v}" for k, v in speaker.stats.items())
            tail.append(f"Your current state: {flat}")
    if speaker.recent_lines:
        anchors = "  ".join(f"“{line}”" for line in speaker.recent_lines)
        tail.append(f"Your recent lines (a reference for your voice, not a script): {anchors}")
    if relationship_note:
        # How this character actually relates to whom they're addressing (from the graph,
        # incl. 2-hop shared ties) so the reply is relationship-appropriate (D4).
        tail.append(f"Your ties in this scene: {relationship_note}")
    if scene_direction.strip():
        # Where the player is steering the scene. Every speaker sees it — including one with
        # no requirement of their own — so the whole cast plays toward the same destination
        # instead of only the character who happens to be carrying a beat of it.
        tail.append(f"Where this scene is going (the player's direction): {scene_direction.strip()}")

    # Situational adaptation cue (recency, strongest attention): read the moment before
    # defaulting to habit, and point at the character's own condition so the
    # manner-adaptation rule actually fires. The mood is deliberately NOT restated from
    # ``ctx.setting`` — that text is authored at world creation and never updated during
    # play, so asserting it as "the scene right now" pinned every beat to the scene's
    # opening tone. What is happening now comes from the beats above.
    directive_text = _REGISTER_DIRECTIVES.get(register or "")
    if directive_text:
        # The scene director already read the moment for this beat — hand the speaker the
        # ANSWER rather than the question, so it does not have to out-argue its own voice
        # samples to reach it. Stakes name the concrete thing at risk.
        moment = directive_text
        if stakes:
            moment += f" What is at stake right now: {stakes}."
        moment += " Let that reach your voice — don't answer on autopilot."
        tail.append(moment)
    else:
        tail.append(
            "Before you respond, read the moment as the beats above actually show it — what has "
            "just changed, how much danger or feeling is in the air, and your own condition — and "
            "let it shape how you come across. Drop your usual manner if the moment calls for it "
            "(grief, fear, urgency, tenderness); don't answer on autopilot."
        )
    if ctx.directed_at == speaker.id:
        tail.append("The player addressed you directly.")
    if speaker.disposition:
        # Carried in from the previous turn's reflection (§P9). This is the only signal in
        # the prompt that tracks how events have actually CHANGED this character, so it sits
        # in the recency TAIL beside the register rather than above the voice samples,
        # which would outweigh it.
        tail.append(
            f"You do not come into this beat neutral. Where the last one left you: "
            f"{speaker.disposition} That is your condition now — carry it in. If it means "
            "you cannot keep up your usual manner, don't; let <thinking> build on it in "
            "your own voice rather than restating it."
        )
    if directive:
        # Puppet performance (D1): the player directed you — perform it in your own voice.
        tail.append(
            f"The player is directing you to: {directive}. Do it now in {speaker.name}'s own "
            "voice and personality — make it yours, don't quote the player. "
            "Emit only the tagged format."
        )
    else:
        tail.append(
            f"Respond now, in {speaker.name}'s voice, to what was just said. "
            "Emit only the tagged format."
        )
    owed = [r.strip() for r in (requirements or []) if r and r.strip()]
    if owed:
        # LAST, where attention is strongest: what this beat has to accomplish. Stated as an
        # outcome rather than a script — the player said WHAT happens, the character still
        # owns HOW. Everything above (voice, state, the manner-adaptation rule) still binds.
        must = "; ".join(owed)
        tail.append(
            f"THIS BEAT MUST MAKE THIS TRUE: {must}. It is the player's direction and it "
            f"happens now — not later, not maybe. How you get there is yours: reach it as "
            f"{speaker.name} genuinely would, in your own words, manner, and reasoning. Never "
            "quote or paraphrase the direction itself, never narrate it as an outside voice, "
            "and never break character to acknowledge it."
        )

    return "\n".join(["\n".join(stable), "", "\n".join(middle), "", "\n".join(tail)])


# Cap the rendered transcript so a crowded, many-speaker turn keeps the prompt bounded
# (§P10 — "bookended prompt under scale"). The most recent beats matter most for recency;
# older context lives in the buffer/graph, not this window. The depth is the per-scene
# ``context_beats`` (5–100); this is only the fallback when it is unset.
_TRANSCRIPT_MAX_BEATS = 14


def _transcript(ctx: TurnContext, turn_beats: list[dict]) -> str:
    """Render prior history + this-turn beats as a short transcript (chronological).

    The window depth is the scene's ``context_beats`` — the same "how much context the
    character sees" the player configures.

    The cap here allows a whole anchor block ABOVE that depth on purpose. ``recent_beats``
    already arrives block-anchored (``buffer.anchored_turns``), which is what holds the
    transcript's first line still between re-anchors; re-trimming it to exactly
    ``context_beats`` here would slide the start by one beat per turn again and undo the
    anchoring entirely — the prompt-cache prefix would collapse back to the system message.
    """
    names = {m.id: m.name for m in ctx.cast}
    depth = max(1, ctx.context_beats or _TRANSCRIPT_MAX_BEATS)
    depth += max(1, get_settings().turn_transcript_anchor_block)
    lines: list[str] = []
    for beat in [*ctx.recent_beats, *turn_beats][-depth:]:
        text = str(beat.get("text", "")).strip()
        if not text:
            continue
        role = beat.get("role")
        if role == "player":
            who = "Player"
        elif role == "narrator":
            who = "Narrator"
        else:
            cid = beat.get("characterId")
            who = names.get(cid, "Someone") if cid else "Someone"
        lines.append(f"{who}: {text}")
    return "\n".join(lines)
