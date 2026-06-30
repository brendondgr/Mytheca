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

from sqlalchemy.orm import Session

from app.agents._common import gen_params, resolve_llm
from app.schemas.reasoning import ReasoningEffort
from app.services import llm
from app.services.assembler import CastMember, TurnContext

# A spoken line wants minimal *hidden* reasoning (voice comes from the prompt, not a
# long internal monologue); keep the thinking budget low so the turn stays snappy.
TURN_EFFORT = ReasoningEffort.LOW

_OUTPUT_CONTRACT = """You voice exactly ONE character in a living, in-progress scene. Stay fully in character.

Emit ONLY this format and nothing else — no preamble, no markdown, no commentary:
<speaker:N>
<type:character_action>
{a short third-person beat of what your character physically does, present tense — optional}
<type:character_dialogue>
{your character's spoken line}

Rules:
- N is your character's roster number (given below).
- Always include character_dialogue. Include character_action only when your character does something physical.
- Never narrate or speak for any other character; react only as your character.
- Keep it tight and in-voice — one beat, the spoken line, nothing more."""


def generate_line(
    db: Session,
    ctx: TurnContext,
    speaker: CastMember,
    player_text: str,
    *,
    reasoning: ReasoningEffort = TURN_EFFORT,
) -> str:
    """Generate one character's raw emission for this beat (thin-tag format)."""
    base_url, api_key, model, params = resolve_llm(db)
    system = f"{_OUTPUT_CONTRACT}\n\n{ctx.stable_prefix}".strip()
    user = _build_user_prompt(ctx, speaker, player_text)
    return llm.chat_complete(
        base_url,
        api_key,
        model,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        gen_params(params),
        reasoning=reasoning,
    )


def _speaker_number(ctx: TurnContext, speaker: CastMember) -> int:
    for i, member in enumerate(ctx.cast):
        if member.id == speaker.id:
            return i + 1
    return 1


def _build_user_prompt(ctx: TurnContext, speaker: CastMember, player_text: str) -> str:
    """Bookended volatile suffix: identity/state (front) · scene+transcript (middle) · act-now (tail)."""
    number = _speaker_number(ctx, speaker)

    # HEAD — identity + interiority (primacy).
    head = [f"You are [{number}] {speaker.name} — {speaker.role}."]
    if speaker.speech:
        head.append(f"Speech style: {speaker.speech}")
    if speaker.traits:
        head.append(f"Traits: {speaker.traits}")
    if speaker.stats:
        state = ", ".join(f"{k}={v}" for k, v in speaker.stats.items())
        head.append(f"Your current state: {state}")
    if speaker.recent_lines:
        anchors = "  ".join(f"“{line}”" for line in speaker.recent_lines)
        head.append(f"Your recent lines (match this voice): {anchors}")

    # MIDDLE — scene + roster + transcript (context, not driver).
    middle: list[str] = []
    if ctx.setting is not None:
        flavor = ctx.setting.atmosphere or ctx.setting.current_state or ctx.setting.desc or ""
        middle.append(f"Setting: {ctx.setting.name}{(' — ' + flavor) if flavor else ''}.")
    roster = ", ".join(f"[{i + 1}] {m.name}" for i, m in enumerate(ctx.cast))
    middle.append(f"Cast in the scene: {roster}.")
    transcript = _transcript(ctx)
    if transcript:
        middle.append(f"Recent beats:\n{transcript}")
    directed = " (directed at you)" if ctx.directed_at == speaker.id else ""
    middle.append(f'The player just did: "{player_text}"{directed}.')

    # TAIL — act-now (recency).
    tail = f"Respond now, in {speaker.name}'s voice, to what was just said. Emit only the tagged format."

    return "\n".join(["\n".join(head), "", "\n".join(middle), "", tail])


def _transcript(ctx: TurnContext) -> str:
    """Render the recent buffer as a short transcript (best-effort; may be empty)."""
    names = {m.id: m.name for m in ctx.cast}
    lines: list[str] = []
    for beat in ctx.recent_beats:
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
