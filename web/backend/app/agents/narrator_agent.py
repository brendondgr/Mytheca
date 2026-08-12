"""Narrator agent — the optional interstitial beat (Narrator Mode only).

Narration is a *decoration* on the one POV loop, not a separate engine (D1): in
Narrator Mode a short, third-person environmental/transition beat is inserted where a
transition needs it; in POV Mode it is off (environment rides inside a character's
perception instead). Best-effort: a missing/failed LLM yields ``None`` and the turn
simply skips the interstitial.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents import prompt_registry
from app.agents._common import gen_params, resolve_llm
from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.services import llm
from app.services.assembler import TurnContext

NARRATOR_EFFORT = ReasoningEffort.LOW

# Default narration text now lives in ``prompt_registry`` (single source of truth for
# editable writing prompts). Base beat = a couple of vivid sentences that PROGRESS the
# scene; the ``long`` variant is a full paragraph used to OPEN a scene or play out a
# branch. Resolved per-turn text rides on ``ctx.prompts``.
_SYSTEM = prompt_registry.default(prompt_registry.NARRATOR_SYSTEM)
_SYSTEM_LONG = prompt_registry.default(prompt_registry.NARRATOR_SYSTEM_LONG)


def interstitial(
    db: Session,
    ctx: TurnContext,
    turn_beats: list[dict],
    *,
    lead: str | None = None,
    long: bool = False,
) -> str | None:
    """Generate a narration beat, or ``None`` (best-effort) to skip it.

    ``long`` swaps the short transition beat for a fuller paragraph that advances the
    story (used to OPEN a scene and to play out a selected branch — the player asked the
    story to move, so narration covers the next few moments rather than stopping short).
    ``lead`` folds an explicit cue into the prompt (the branch's narrative direction, a
    scene-opening hint, or — under Narrator-Guided Scenes — the player's scene direction
    plus the specific outcomes THIS beat owes) so the beat leans into where the player is
    steering. The turn engine composes it; this agent just places it above the transcript,
    where it reads as the destination for the prose rather than as text to restate.
    """
    try:
        base_url, api_key, model, params = resolve_llm(db)
    except APIError:
        return None

    setting = ""
    if ctx.setting is not None:
        flavor = ctx.setting.atmosphere or ctx.setting.current_state or ctx.setting.desc or ""
        setting = f"Setting: {ctx.setting.name}{(' — ' + flavor) if flavor else ''}.\n"
    transcript = _recent(ctx, turn_beats)
    lead_line = f"Direction to follow: {lead}\n" if lead else ""
    ask = (
        "Write the narrator's opening/progression passage now."
        if long
        else "Write the narrator's transition beat now."
    )
    user = f"{setting}{lead_line}Recent beats:\n{transcript}\n\n{ask}"
    system = (
        ctx.prompts.get(prompt_registry.NARRATOR_SYSTEM_LONG, _SYSTEM_LONG)
        if long
        else ctx.prompts.get(prompt_registry.NARRATOR_SYSTEM, _SYSTEM)
    )

    try:
        text = llm.chat_complete(
            base_url,
            api_key,
            model,
            [{"role": "system", "content": f"{system}\n\n{ctx.stable_prefix}".strip()},
             {"role": "user", "content": user}],
            gen_params(params),
            reasoning=NARRATOR_EFFORT,
        )
    except APIError:
        return None
    # `chat_complete` already sanitizes reasoning/channel leakage centrally (see
    # `_common.strip_reasoning`), so the freeform narration arrives clean.
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
