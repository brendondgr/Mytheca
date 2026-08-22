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
from app.schemas.base import DEFAULT_BEAT_LENGTH
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

# Sampler tuning for in-character voice on small models (the turn-loop plan §7): a lower
# top_p reins in drift more reliably than raising temperature. Applied per turn-call (a
# per-storyline/character voice setting is a recorded seam). Temperature + max_tokens are
# kept from the operator's config.
#
# The frequency/presence penalties that used to sit here are ZERO, and that is a measured
# decision rather than a default. EXP-2026-08-007 ran three arms, n=10 each, on the live
# endpoint with only these two fields varying. They fall on every token, and the tokens
# prose is made of are its most repeated ones — the full stop, the comma, the double quote,
# "I", "the" — so penalising them penalises sentences:
#
#     sentences per 100 words   0.40/0.30: 1.32 ± 1.16   0.20/0.15: 3.80 ± 3.07   off: 11.42 ± 3.96
#     passages containing speech       80%                     70%                    100%
#     characters per passage    2183 ± 1771            1919 ± 1883             674 ± 471
#
# The arms do not overlap on the primary metric: the worst run with the penalties off
# (8.9) beats the best run with them on (3.7). They are also what made length
# uncontrollable — the rambling that a passage ceiling was once added to contain was the
# penalties, not the freedom.
#
# The trade, stated rather than made quietly: the penalties were added to fight in-character
# drift, and removing them may bring some of it back. Grammar first. A repetitive but
# well-formed paragraph is readable; a punctuation-free 180-word sentence is not.
_VOICE_TOP_P = 0.92
_VOICE_FREQUENCY_PENALTY = 0.0
_VOICE_PRESENCE_PENALTY = 0.0

# Per-register sampler tuning: (top_p, frequency_penalty, presence_penalty).
#
# ``top_p`` narrows as the moment gets graver, so a grave beat stays on the obvious,
# sincere word while a light one can reach for the unexpected one. That is a choice about
# WORD CHOICE and it survives.
#
# The penalties are zero at every register. They used to rise for a light moment
# (0.45/0.35) on the theory that banter should stay varied — which made the LIGHTEST beats
# the most damaged ones, and is visible in the ps_c015c506b1 export, where the banter beat
# came back as "There — *chirp!* — there you are ! Just one sip … no wait" with no sentence
# in it. See ``_VOICE_FREQUENCY_PENALTY`` above for the measurement (EXP-2026-08-007).
# The column is kept rather than removed so the shape of the table stays obvious and a
# future measurement can put something back in it.
#
# A beat with no register (planner fallback, puppet beat, test context) resolves to the
# module defaults above. Temperature and max_tokens stay under the operator's config.
_REGISTER_SAMPLER = {
    "light": (0.95, 0.0, 0.0),
    "neutral": (0.92, 0.0, 0.0),
    "tense": (0.88, 0.0, 0.0),
    "grave": (0.85, 0.0, 0.0),
}

#: How far one step of a character's ``looseness`` moves the register's ``top_p``, and the
#: bounds it is clamped into.
#:
#: ``looseness`` is a **bias on top of the beat's register**, not a replacement for it — the
#: moment picks the row and this leans against it.
#:
#: One notch is 0.03, which is exactly the smallest gap between two adjacent register rows
#: (light 0.95 · neutral 0.92 · tense 0.88 · grave 0.85). So a single notch moves a beat by
#: at most one row's worth, and the register still leads.
#:
#: **At the extremes it does cross rows, and that is worth knowing rather than hiding.** The
#: full ±2 range spans 0.12 against a register span of 0.10, so a ``+2`` character on a grave
#: beat samples at 0.91 — looser than ``tense``. That is the intended meaning of an extreme
#: setting ("this person rambles even at a funeral"), but it means the dial is not strictly
#: subordinate to the moment at ±2. The step size is **chosen, not measured**; the experiment
#: that would settle it is named in ``docs/checklist.md``.
_LOOSENESS_STEP = 0.03
_LOOSENESS_BOUNDS = (0.70, 0.98)

# **``top_p`` ONLY. The penalty columns stay 0.0 at every combination, and this dial must
# never be extended to them.** EXP-2026-08-007 measured frequency/presence penalties
# degrading the sentence structure of character prose — they fall on the punctuation and
# function words prose is made of, and the arms did not overlap. Widening a "looseness"
# control onto that axis would reintroduce, as a feature, the exact defect that experiment
# was run to remove. The checklist names the drift eval that would have to come first.

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

# How much this character says in one beat — the per-scene ``beat_length``, set from the
# scene config menu. Stated as a PARAGRAPH count, deliberately, and never as a word count.
#
# A countable word target has already been tried on this codebase and failed: a "usually
# 80–200 words" instruction moved the average passage *up* rather than down
# (EXP-2026-08-007 § Secondary finding). A model cannot count words while writing, so a
# numeric target reads to it as a description of the register — long, careful prose — and it
# obliges. Paragraphs are different in kind: the model is already producing them
# deliberately and reliably (3.89 ± 1.29 measured in EXP-2026-08-009), so a paragraph count
# asks it to control an axis it already controls.
#
# Quoted dialogue is exempted from the per-paragraph sentence guidance in so many words. A
# spoken line is not a sentence of description, and charging it as one would make the
# instruction trade away the very thing the prose fix was for.
#
# The tiers are the owner's, verbatim. Note that ``long`` is LONGER than what shipped before
# this control existed; ``medium`` is the default and the closest match to it.
_BEAT_LENGTH_DIRECTIVES = {
    "short": (
        "LENGTH: keep this beat SHORT — one or two paragraphs, no more. Say the one thing "
        "that matters and stop; leave the rest for your next turn."
    ),
    "medium": (
        "LENGTH: two to four paragraphs for this beat."
    ),
    "long": (
        "LENGTH: give this beat room — five or six paragraphs. Let it breathe: what you "
        "notice, what you do, what you say, and what it costs you."
    ),
}
#: Appended to whichever directive applies. Split out because it is the same rule at every
#: tier and repeating it three times invites the three copies to drift.
_BEAT_LENGTH_SHAPE = (
    " Keep each paragraph to three or four sentences at most — lines of spoken dialogue do "
    "not count toward that."
)

# Default output contract text now lives in ``prompt_registry`` (single source of truth
# for editable writing prompts); resolved per-turn text rides on ``ctx.prompts``.
_OUTPUT_CONTRACT = prompt_registry.default(prompt_registry.CHARACTER_OUTPUT_CONTRACT)


#: Room for the passage itself, in tokens — roughly 8,000 characters, or 1,300 words.
#:
#: This is NOT an editorial limit. Nothing in the contract tells a character to be brief,
#: and the owner asked twice for one to be able to speak for as long as they want. What it
#: stops is the OPERATOR'S GLOBAL ``maxTokens`` being spent on a single spoken beat. That
#: field is one number shared with every authoring flow — world building, storyline
#: generation — where a very long output is the point; on this install it is 48,000. Passing
#: it through to a character beat is how one live generation ran to 48,000 completion tokens
#: over 684 seconds, timed out the relay's health probe three times, left the upstream marked
#: failed, and 400'd the next three turns. One beat cost the player the rest of the scene.
#:
#: The value is set from measurement, not caution. With the sampler fixed (EXP-2026-08-007) a
#: passage averages 674 ± 471 characters and the longest of thirty was 1,923 — so 2,048
#: tokens is about four times the worst honest case and will not be reached by writing.
#: An earlier ceiling of 1,200 WAS an editorial one, imposed on the theory that uncapped
#: passages rambled; that theory was wrong (the rambling was the sampler) and it is gone.
#:
#: Set to ``None`` to hand the operator's own ``maxTokens`` to every beat; the streaming
#: stop in ``turn_engine._RUNAWAY_CHARS`` is then the only thing between a runaway and the
#: endpoint.
_VOICE_PROSE_TOKENS: int | None = 2048

#: The same allowance, per ``beat_length`` tier — a BACKSTOP behind the prompt directive,
#: not the mechanism. The directive in the recency TAIL is what shapes a beat; this is what
#: stops a tier the directive fails to bind from producing its neighbour's output.
#:
#: Sized at roughly **three times** what each tier actually needs, on the same reasoning as
#: the value above: a paragraph of four sentences runs about 400–500 characters ≈ 120
#: tokens, so `short` needs ~240, `medium` ~480 and `long` ~720. Anything tighter would make
#: the cap the thing shaping the prose, and a token cap shapes prose by cutting it off
#: mid-sentence — a worse artifact than a beat that runs one paragraph over. `long` keeps the
#: measured 2,048 exactly, so nothing about the longest tier changes from what shipped.
#:
#: Note this bounds the PROSE half only. ``_voice_params`` adds the thinking budget on top;
#: shrinking the combined total is what starved a live beat into returning reasoning and no
#: prose, and that structure is deliberately preserved here.
_PROSE_TOKENS_BY_LENGTH: dict[str, int] = {
    "short": 700,
    "medium": 1400,
    "long": 2048,
}

#: How much of the thinking budget to actually pay for. ``thinking_token_budget`` is a hint
#: on this endpoint, not a hard stop, so a deliberation can run past it and eat the room the
#: passage needs — which is how a beat in the live verification run came back as reasoning
#: with no prose. Two is generous enough that the overshoot never reaches the passage and
#: costs nothing when it does not happen: the model stops when it is done, not at the cap.
_SCRATCHPAD_HEADROOM = 2


def prose_tokens_for(beat_length: str | None) -> int | None:
    """The prose allowance for a tier, or ``None`` when the bound is switched off entirely.

    Public because ``turn_engine`` derives its streaming runaway stop from the same number —
    two independently-chosen limits for the same thing is how one of them ends up wrong.
    """
    if not _VOICE_PROSE_TOKENS:
        return None
    return _PROSE_TOKENS_BY_LENGTH.get(beat_length or "", _VOICE_PROSE_TOKENS)


def _voice_params(
    params: LlmParams,
    register: str | None = None,
    reasoning: ReasoningEffort = TURN_EFFORT,
    beat_length: str | None = None,
    looseness: int | None = None,
) -> LlmParams:
    """Bound the beat generously and apply the voice-tuned sampler fields.

    The sampler tracks the beat's ``register`` (see ``_REGISTER_SAMPLER``); an absent or
    unrecognized register keeps the module defaults.

    ``looseness`` is the speaker's own bias on top of that, in ``[-2, +2]``, moving ``top_p``
    by :data:`_LOOSENESS_STEP` per step and clamped into :data:`_LOOSENESS_BOUNDS`. ``None``
    is byte-identical to no looseness at all. **It moves ``top_p`` and nothing else** — see
    the constant's comment for why the penalty columns are held at zero.

    ``max_tokens`` buys the hidden thinking **and** the answer out of one budget, so the
    passage allowance is added ON TOP of the thinking budget rather than shared with it.
    Capping the request at the passage allowance alone starves the answer: with the two set
    equal at 1,200, a live turn spent the whole budget deliberating and came back as
    reasoning with no prose at all ("the model spent its whole budget thinking and never
    answered").

    The scratchpad is given :data:`_SCRATCHPAD_HEADROOM` times its budget, because
    ``thinking_token_budget`` is a HINT on this endpoint rather than a hard stop — a probe
    at a 1,024-token budget came back with 4,193 and 3,121 characters of reasoning, which
    hovers at the budget and can pass it. Without the headroom a long deliberation eats the
    passage's room and the beat returns nothing; a beat starved exactly this way in the live
    verification run. It costs nothing when it is not used, since the model stops on its own.

    The cap applies to the ``gen_params`` floor, not to the operator's raw ``max_tokens`` —
    that field defaults to 512, which is a default rather than a choice and would starve
    every beat on a stock install.
    """
    top_p, frequency, presence = _REGISTER_SAMPLER.get(
        register or "", (_VOICE_TOP_P, _VOICE_FREQUENCY_PENALTY, _VOICE_PRESENCE_PENALTY)
    )
    if looseness:
        low, high = _LOOSENESS_BOUNDS
        top_p = round(min(high, max(low, top_p + looseness * _LOOSENESS_STEP)), 4)
    tuned = gen_params(params).model_copy(
        update={
            "top_p": top_p,
            "frequency_penalty": frequency,
            "presence_penalty": presence,
        }
    )
    prose = prose_tokens_for(beat_length)
    if not prose:
        return tuned
    budget = budget_for(reasoning) * _SCRATCHPAD_HEADROOM + prose
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
        _voice_params(
            params, register, reasoning, getattr(ctx, "beat_length", DEFAULT_BEAT_LENGTH),
            looseness=getattr(speaker, "looseness", None),
        ),
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
            _voice_params(
                params, register, reasoning, getattr(ctx, "beat_length", DEFAULT_BEAT_LENGTH),
                looseness=getattr(speaker, "looseness", None),
            ),
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
    # The scene's memory of beats that have fallen out of the window, at the HEAD of the
    # append-only region. The placement is deliberate and load-bearing: the summary only
    # changes when compaction fires, which is also exactly when the anchored window
    # re-anchors — so the two invalidate the cache prefix *together*, on one turn, instead
    # of on two different ones.
    if ctx.history_summary:
        middle.append(f"Earlier in this scene (summary):\n{ctx.history_summary}")
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
    # How much to say. In the TAIL, not the STABLE head: it is per-scenario, and a
    # per-scenario value in the head would break the byte-stable prompt-cache prefix
    # (`test_prompt_cache_prefix.py`). Placed after the register directive — which shapes
    # *how* the beat sounds — because length is a property of the delivery, not of the
    # moment, and before the owed-requirements block, which has to stay last.
    tail.append(
        _BEAT_LENGTH_DIRECTIVES.get(
            getattr(ctx, "beat_length", DEFAULT_BEAT_LENGTH), _BEAT_LENGTH_DIRECTIVES["medium"]
        )
        + _BEAT_LENGTH_SHAPE
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
# ``window_beats`` — fitted to the model's real context budget each turn, or the scene's own
# ``context_beats`` when it opted out. This is only the fallback when neither is set.
_TRANSCRIPT_MAX_BEATS = 14


def _transcript(ctx: TurnContext, turn_beats: list[dict]) -> str:
    """Render prior history + this-turn beats as a short transcript (chronological).

    The window depth is ``ctx.window_beats`` — fitted to the model's real context budget by
    ``services/context_budget`` (or the scene's own ``context_beats`` when it opted out of
    the auto policy). It is no longer a number the player picks: that asked them a question
    only the app can answer.

    The cap here allows a whole anchor block ABOVE that depth on purpose. ``recent_beats``
    already arrives block-anchored (``buffer.anchored_turns``), which is what holds the
    transcript's first line still between re-anchors; re-trimming it to exactly
    the fitted depth here would slide the start by one beat per turn again and undo the
    anchoring entirely — the prompt-cache prefix would collapse back to the system message.
    """
    names = {m.id: m.name for m in ctx.cast}
    # `window_beats` alone, not `window_beats or context_beats`. Under the fixed policy the
    # assembler sets them equal, so a fallback chain would never change an outcome — but it
    # WOULD let a caller set one and be silently given the other, which is precisely the
    # surprise this file's own test caught.
    depth = max(1, ctx.window_beats or _TRANSCRIPT_MAX_BEATS)
    depth += max(1, get_settings().turn_transcript_anchor_block)
    lines: list[str] = []
    for beat in [*ctx.recent_beats, *turn_beats][-depth:]:
        text = str(beat.get("text", "")).strip()
        if not text:
            continue
        role = beat.get("role")
        if role == "player":
            # NOT "Player". That label was the only name the model had for the person in
            # the room with it, and it used it: 13 of 18 character beats in the
            # EXP-2026-08-008 verification run wrote "the player" into the prose. Every
            # other line here carries a character's name, including this speaker's own, so
            # "You" is unambiguous — and it is already the form the passage should use.
            who = "You"
        elif role == "narrator":
            who = "Narrator"
        else:
            cid = beat.get("characterId")
            who = names.get(cid, "Someone") if cid else "Someone"
        lines.append(f"{who}: {text}")
    return "\n".join(lines)
