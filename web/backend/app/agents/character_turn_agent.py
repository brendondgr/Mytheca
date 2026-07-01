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

from app.agents._common import gen_params, resolve_llm
from app.schemas.reasoning import ReasoningEffort
from app.schemas.settings import LlmParams
from app.services import llm
from app.services.assembler import CastMember, TurnContext

logger = logging.getLogger("velora.turn")

# A spoken line wants minimal *hidden* reasoning (voice comes from the prompt + the
# short visible thinking block, not a long internal monologue); keep the hidden
# thinking budget low so the turn stays snappy.
TURN_EFFORT = ReasoningEffort.LOW

# Sampler tuning for in-character voice on small models (the turn-loop plan §7):
# repetition/frequency penalties + a lower top_p rein in drift more reliably than
# raising temperature. Applied per turn-call (a per-storyline/character voice setting
# is a recorded seam). Temperature + max_tokens are kept from the operator's config.
_VOICE_TOP_P = 0.92
_VOICE_FREQUENCY_PENALTY = 0.4
_VOICE_PRESENCE_PENALTY = 0.3

_OUTPUT_CONTRACT = """You voice exactly ONE character in a living, in-progress scene. Stay fully in character.

Emit ONLY this format and nothing else — no preamble, no markdown, no commentary:
<speaker:N>
<thinking>
{a SHORT thought in your character's own voice — your standpoint and what you want right now, not analysis. One or two clipped sentences. This is private and is never shown to anyone.}
</thinking>
<type:character_action>
{a SHORT third-person beat of what your character physically does, present tense — 5-10 words MAX, optional}
<type:character_dialogue>
{your character's spoken line — 1-3 sentences, natural and in-voice}

You MAY, only when this beat genuinely moves a tracked stat, add a state_update block with a stat JSON:
<type:state_update>
{"key": "<stat key>", "delta": <signed integer>, "reason": "<short why>"}

You MAY, only when this beat genuinely changes how you regard another character, add a relationship_update block:
<type:relationship_update>
{"target": "<the other character's name>", "type": "<trusts|fears|resents|loves|allied_with|at_war_with|knows|suspects>", "reason": "<short why>"}

Rules:
- N is your character's roster number (given below).
- Write each block's OPENING tag only (e.g. `<type:character_dialogue>`); do NOT write closing tags like `</type:character_dialogue>`.
- Lead with <thinking>: a brief, in-*your*-voice thought that sets up your line (e.g. "Coin first, favor later — let him sweat."). Think in the SAME voice as your speech style and voice samples — the private thought should sound like you, not like a narrator. Condition it on concrete priorities, never on a trait label; keep it clipped, never a formal narrator's analysis.
- Always include character_dialogue. Include character_action only when your character does something physical — keep it to a SHORT label of 5-10 words (it renders as a brief tag beside your name, e.g. "leans in, low"), never a full sentence.
- Use state_update only for a real shift in a stat listed in "Your current state", with a short reason — never invent a stat key. Most turns move nothing; omit it then.
- Use relationship_update only for a real shift in how you regard a specific other character (name them exactly). Most turns change nothing; omit it then.
- Never narrate or speak for any other character; react only as your character.
- Keep it tight and in-voice — the thought, one beat, the spoken line, an optional stat shift, nothing more."""


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
    system = f"{_OUTPUT_CONTRACT}\n\n{ctx.stable_prefix}".strip()
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
        # Disposition already computed (§P9) — keep the hidden reasoning to a beat.
        tail.append("You already know your stance — keep <thinking> to a few words.")
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
# most for recency; older context lives in the buffer/graph, not this window.
_TRANSCRIPT_MAX_BEATS = 14


def _transcript(ctx: TurnContext, turn_beats: list[dict]) -> str:
    """Render prior history + this-turn beats as a short transcript (chronological)."""
    names = {m.id: m.name for m in ctx.cast}
    lines: list[str] = []
    for beat in [*ctx.recent_beats, *turn_beats][-_TRANSCRIPT_MAX_BEATS:]:
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
