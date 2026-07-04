"""Character turn agent — voice ONE character for the current beat.

One LLM call per active speaker (per-character isolation — no shared multi-POV
prompt, so voices stay distinct). The model emits the thin tag format
(``<speaker:N>`` + ``<type:...>`` + free prose); the backend owns the envelope
(``services.emission``). The prompt is **bookended** (the turn-loop plan §11.4): the
character's identity + state lead (primacy), the transcript sits in the middle, and
the "respond now" instruction is last (recency). The cacheable stable region (World
Primer + stat guidance) rides in the system message.

P3 is single-pass (speak only). The hidden ``<thinking>`` conditioning block + in-voice
sampler tuning are layered on in the think→speak phase; this module is where they land.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.agents import prompt_registry
from app.agents._common import gen_params, resolve_llm
from app.schemas.reasoning import ReasoningEffort
from app.schemas.settings import LlmParams
from app.services import llm
from app.services.assembler import CastMember, TurnContext

logger = logging.getLogger("velora.turn")

# The visible <thinking> block is a real, in-voice deliberation (a short paragraph — a
# person thinks through a situation before speaking), so the character needs room to
# reason before emitting. MEDIUM gives that headroom without making the turn sluggish.
TURN_EFFORT = ReasoningEffort.MEDIUM

# Sampler tuning for in-character voice on small models (the turn-loop plan §7):
# repetition/frequency penalties + a lower top_p rein in drift more reliably than
# raising temperature. Applied per turn-call (a per-storyline/character voice setting
# is a recorded seam). Temperature + max_tokens are kept from the operator's config.
_VOICE_TOP_P = 0.92
_VOICE_FREQUENCY_PENALTY = 0.4
_VOICE_PRESENCE_PENALTY = 0.3

# Default output contract text now lives in ``prompt_registry`` (single source of truth
# for editable writing prompts); resolved per-turn text rides on ``ctx.prompts``.
_OUTPUT_CONTRACT = prompt_registry.default(prompt_registry.CHARACTER_OUTPUT_CONTRACT)


def _voice_params(params: LlmParams) -> LlmParams:
    """Floor max_tokens (reasoning headroom) and apply the voice-tuned sampler fields."""
    return gen_params(params).model_copy(
        update={
            "top_p": _VOICE_TOP_P,
            "frequency_penalty": _VOICE_FREQUENCY_PENALTY,
            "presence_penalty": _VOICE_PRESENCE_PENALTY,
        }
    )


def generate_line(
    db: Session,
    ctx: TurnContext,
    speaker: CastMember,
    *,
    turn_beats: list[dict],
    reasoning: ReasoningEffort = TURN_EFFORT,
    correction: str | None = None,
    directive: str | None = None,
    relationship_note: str | None = None,
) -> str:
    """Generate one character's raw emission for this beat (thin-tag format).

    ``turn_beats`` is the chronological this-turn transcript so far (the player's
    line, then any earlier speakers' lines) — so a later speaker genuinely reacts to
    its predecessor (the immediate predecessor sits last, where recency attention is
    strongest). ``correction`` re-runs the beat after the consistency guard (§P10)
    flagged a continuity break, folding the reason into the act-now tail. ``directive``
    is a **puppet** performance (Reactive Turn Director D1): the player directed this
    character to do/say something, so the character performs it **in their own voice**
    rather than reacting to the player's words as if spoken to them.
    """
    base_url, api_key, model, params = resolve_llm(db)
    contract = ctx.prompts.get(prompt_registry.CHARACTER_OUTPUT_CONTRACT, _OUTPUT_CONTRACT)
    system = f"{contract}\n\n{ctx.stable_prefix}".strip()
    # The system message is byte-identical for every speaker this turn — log its
    # prefix-cache id so warm-prefix reuse across the turn's calls is observable (§P11).
    logger.debug("turn speaker=%s prefix-cache=%s", speaker.id, llm.prefix_cache_key(system))
    user = _build_user_prompt(
        ctx, speaker, turn_beats, correction=correction, directive=directive,
        relationship_note=relationship_note,
    )
    return llm.chat_complete(
        base_url,
        api_key,
        model,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        _voice_params(params),
        reasoning=reasoning,
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
    correction: str | None = None,
    directive: str | None = None,
    relationship_note: str | None = None,
) -> str:
    """Bookended volatile suffix: identity/state (front) · scene+transcript (middle) · act-now (tail)."""
    number = _speaker_number(ctx, speaker)

    # HEAD — identity + interiority (primacy).
    head = [f"You are [{number}] {speaker.name} — {speaker.role}."]
    if speaker.speech:
        head.append(f"Speech style: {speaker.speech}")
    if speaker.traits:
        head.append(f"Traits: {speaker.traits}")
    if speaker.voice_samples:
        # Concrete situation → sample-response pairs authored for this character:
        # the ground truth for *how* they sound. Anchors both the spoken line and
        # the in-voice <thinking> step (Character Voice & Tone).
        head.append(
            "Voice samples — how you sound (match this cadence, diction, and attitude "
            f"in both speech and thought):\n{speaker.voice_samples}"
        )
    if speaker.stats:
        state = ", ".join(f"{k}={v}" for k, v in speaker.stats.items())
        head.append(f"Your current state: {state}")
    if speaker.disposition:
        # Carried in from the previous turn's reflection (§P9): the stance you already
        # hold as you re-enter. It seeds this beat so <thinking> can stay very short.
        head.append(f"Your current inner stance: {speaker.disposition}")
    if speaker.recent_lines:
        anchors = "  ".join(f"“{line}”" for line in speaker.recent_lines)
        head.append(f"Your recent lines (match this voice): {anchors}")

    # MIDDLE — scene + roster + transcript (context, not driver). The transcript ends
    # with the most recent line (the player, or the predecessor who just spoke).
    middle: list[str] = []
    if ctx.setting is not None:
        flavor = ctx.setting.atmosphere or ctx.setting.current_state or ctx.setting.desc or ""
        middle.append(f"Setting: {ctx.setting.name}{(' — ' + flavor) if flavor else ''}.")
    roster = ", ".join(f"[{i + 1}] {m.name}" for i, m in enumerate(ctx.cast))
    middle.append(f"Cast in the scene: {roster}.")
    if ctx.retrieved_lore:
        middle.append(ctx.retrieved_lore.strip())  # fenced reference lore (gated)
    if relationship_note:
        # How this character actually relates to whom they're addressing (from the graph,
        # incl. 2-hop shared ties) so the reply is relationship-appropriate (D4).
        middle.append(f"Your ties in this scene: {relationship_note}")
    transcript = _transcript(ctx, turn_beats)
    if transcript:
        middle.append(f"Recent beats:\n{transcript}")

    # TAIL — act-now (recency).
    tail: list[str] = []
    if ctx.directed_at == speaker.id:
        tail.append("The player addressed you directly.")
    if speaker.disposition:
        # Disposition already computed (§P9) — it seeds the stance, but the character still
        # thinks the moment through in-voice rather than clipping it to a few words.
        tail.append("You already hold a stance — let <thinking> build on it in your own voice, don't just restate it.")
    if correction:
        # Consistency guard flagged the prior attempt (§P10) — steer the redo.
        tail.append(
            f"Your previous line broke continuity ({correction}). Redo it consistently "
            "with the established beats above."
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

    return "\n".join(["\n".join(head), "", "\n".join(middle), "", "\n".join(tail)])


# Cap the rendered transcript so a crowded, many-speaker turn keeps the bookended
# prompt bounded (§P10 — "bookended prompt under scale"). The most recent beats matter
# most for recency; older context lives in the buffer/graph, not this window. The depth is
# the per-scene ``context_beats`` (5–100); this is only the fallback when it is unset.
_TRANSCRIPT_MAX_BEATS = 14


def _transcript(ctx: TurnContext, turn_beats: list[dict]) -> str:
    """Render prior history + this-turn beats as a short transcript (chronological).

    The window depth is the scene's ``context_beats`` — the same "how much context the
    character sees" the player configures — capped at the last N combined beats.
    """
    names = {m.id: m.name for m in ctx.cast}
    depth = max(1, ctx.context_beats or _TRANSCRIPT_MAX_BEATS)
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
