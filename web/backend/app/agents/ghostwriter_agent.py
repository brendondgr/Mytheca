"""Ghostwriter — draft the player's own line from what they said they want.

The player types their *intent* ("tell him I don't believe a word of it, but stay
polite") and this writes the line itself, in their character's voice or the narrator's.
The draft lands in the composer for them to keep, rewrite or throw away.

Two things make it safe, and both are structural rather than promised:

* **Nothing is persisted.** No event row, no trace, no buffer push. A ghostwritten line the
  player rejects leaves no trace anywhere — it never entered the record in the first place.
* **It never decides what happens.** It writes one line, from an intent the player already
  chose. It is not asked who speaks next, what changes, or where the scene goes.

Best-effort like every other agent: an unconfigured endpoint raises before the stream opens,
so the UI can point at Options rather than surfacing a raw upstream failure.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Literal

from sqlalchemy.orm import Session

from app.agents import prompt_registry
from app.agents._common import gen_params, resolve_llm
from app.schemas.reasoning import ReasoningEffort
from app.services import llm
from app.services.assembler import TurnContext

#: Writing one line from a stated intent is not a reasoning problem. Keep the budget low —
#: this sits between the player and their own sentence, so latency is felt directly.
GHOSTWRITER_EFFORT = ReasoningEffort.LOW

GhostwriteMode = Literal["character", "narrator"]


def _recent(ctx: TurnContext, limit: int = 8) -> str:
    """The last few beats, so the drafted line answers what was actually just said."""
    names = {m.id: m.name for m in ctx.cast}
    lines: list[str] = []
    for beat in ctx.recent_beats[-limit:]:
        text = str(beat.get("text", "")).strip()
        if not text:
            continue
        role = beat.get("role")
        cid = beat.get("characterId")
        # NOT "The player". That is the exact string EXP-2026-08-008 measured leaking into
        # 72 % of character beats, and which every other transcript renderer was changed to
        # stop emitting. This one survived because the ghostwriter sits off the turn path, so
        # no prose experiment ever scored it. A `player` beat is a Playwright direction (see
        # `character_turn_agent._transcript`), so it is labelled as one.
        who = names.get(str(cid), "Someone") if role == "character" else (
            "Narrator" if role == "narrator" else "Direction"
        )
        lines.append(f"{who}: {text}")
    return "\n".join(lines)


def build_prompt(
    ctx: TurnContext, *, intent: str, pov_id: str | None, mode: GhostwriteMode
) -> tuple[str, str]:
    """The system + user messages for one draft. Split out so it can be tested directly."""
    system = ctx.prompts.get(
        prompt_registry.GHOSTWRITER_LINE,
        prompt_registry.default(prompt_registry.GHOSTWRITER_LINE),
    )

    parts: list[str] = []
    speaker = ctx.cast_by_id(pov_id) if pov_id else None
    if mode == "character" and speaker is not None:
        parts.append(f"You are writing as {speaker.name}.")
        if speaker.role:
            parts.append(f"Their role in the scene: {speaker.role}")
        if speaker.traits:
            parts.append(f"Who they are: {speaker.traits}")
        # `speech` is the authored voice description; `voice_samples` are real lines of
        # theirs. Samples matter more than description here — the draft has to *sound* like
        # them, and a sample shows what description only asserts.
        if speaker.speech:
            parts.append(f"How they speak: {speaker.speech}")
        if speaker.voice_samples:
            parts.append(f"Lines of theirs, for the sound of it:\n{speaker.voice_samples}")
    else:
        parts.append(
            "You are writing the player's own line as the guide/narrator of the scene — "
            "not as any one character."
        )

    recent = _recent(ctx)
    if recent:
        parts.append(f"The scene so far:\n{recent}")
    parts.append(
        "What the player wants this line to do — write the line that does it:\n" + intent.strip()
    )
    return system, "\n\n".join(parts)


def stream_line(
    db: Session,
    ctx: TurnContext,
    *,
    intent: str,
    pov_id: str | None = None,
    mode: GhostwriteMode = "character",
) -> Generator[llm.StreamDelta, None, str]:
    """Stream one drafted line; return the finished text.

    Raises ``APIError`` when no model is configured — deliberately, unlike the turn agents
    which degrade to skipping a beat. Here the player pressed a button and is waiting for a
    sentence: silently producing nothing would read as the button being broken.
    """
    base_url, api_key, model, params = resolve_llm(db)
    system, user = build_prompt(ctx, intent=intent, pov_id=pov_id, mode=mode)
    text, _ = yield from llm.chat_complete_stream(
        base_url,
        api_key,
        model,
        [
            {"role": "system", "content": f"{system}\n\n{ctx.stable_prefix}".strip()},
            {"role": "user", "content": user},
        ],
        gen_params(params),
        reasoning=GHOSTWRITER_EFFORT,
    )
    return text.strip()
