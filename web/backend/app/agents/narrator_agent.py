"""Narrator agent — the optional interstitial beat (Narrator Mode only).

Narration is a *decoration* on the one POV loop, not a separate engine (D1): in
Narrator Mode a short, third-person environmental/transition beat is inserted where a
transition needs it; in POV Mode it is off (environment rides inside a character's
perception instead). Best-effort: a missing/failed LLM yields ``None`` and the turn
simply skips the interstitial.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents._common import gen_params, resolve_llm
from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.services import llm
from app.services.assembler import TurnContext

NARRATOR_EFFORT = ReasoningEffort.LOW

_SYSTEM = """You are the narrator of an interactive scene. Write ONE short, vivid, third-person beat (1-2 sentences) that sets or shifts the moment in response to what just happened — the room, the light, a gesture, the weather. Describe the environment and mood only; never speak for a character or write dialogue. Reply with the prose only — no tags, no quotes, no preamble."""


def interstitial(db: Session, ctx: TurnContext, turn_beats: list[dict]) -> str | None:
    """Generate a short narration beat, or ``None`` (best-effort) to skip it."""
    try:
        base_url, api_key, model, params = resolve_llm(db)
    except APIError:
        return None

    setting = ""
    if ctx.setting is not None:
        flavor = ctx.setting.atmosphere or ctx.setting.current_state or ctx.setting.desc or ""
        setting = f"Setting: {ctx.setting.name}{(' — ' + flavor) if flavor else ''}.\n"
    transcript = _recent(ctx, turn_beats)
    user = f"{setting}Recent beats:\n{transcript}\n\nWrite the narrator's transition beat now."

    try:
        text = llm.chat_complete(
            base_url,
            api_key,
            model,
            [{"role": "system", "content": f"{_SYSTEM}\n\n{ctx.stable_prefix}".strip()},
             {"role": "user", "content": user}],
            gen_params(params),
            reasoning=NARRATOR_EFFORT,
        )
    except APIError:
        return None
    text = text.strip()
    return text or None


def _recent(ctx: TurnContext, turn_beats: list[dict], limit: int = 6) -> str:
    names = {m.id: m.name for m in ctx.cast}
    lines: list[str] = []
    for beat in [*ctx.recent_beats, *turn_beats][-limit:]:
        text = str(beat.get("text", "")).strip()
        if not text:
            continue
        role = beat.get("role")
        cid = beat.get("characterId")
        if role == "player":
            who = "Player"
        elif cid:
            who = names.get(cid, "Someone")
        else:
            who = "Narrator"
        lines.append(f"{who}: {text}")
    return "\n".join(lines) or "(scene opening)"
