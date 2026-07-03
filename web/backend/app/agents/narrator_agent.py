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

# Base beat: a couple of vivid sentences that PROGRESS the scene (narration's job is to
# move the story to the next beat, not to linger on scenery). The ``long`` variant asks
# for a full paragraph used to OPEN a scene or play out a selected branch.
_SYSTEM = """You are the narrator of an interactive scene. Your job is to PROGRESS the story to the next beat — not to linger on scenery. In 2-3 vivid, third-person sentences, narrate what the characters are DOING and carry the moment forward in response to what just happened: follow an action through to its consequence (a swing lands or misses, someone dodges, grabs a weapon, strikes back), show each character's move, and hand the scene to the next beat where someone can react. Lead with action and what people do; touch the setting, light, or mood only as much as it takes to make the action land — never dwell on atmosphere. Never speak for a character or write dialogue. Reply with the prose only — no tags, no quotes, no preamble."""

_SYSTEM_LONG = """You are the narrator of an interactive scene. Write a vivid, third-person passage (a full paragraph, 3-5 sentences) that PROGRESSES the story forward over the next beats in response to what just happened — narrate what each character is DOING and carry the action through to its next consequence (their moves, how they react, the shift set in motion), so the scene arrives somewhere new where a character can respond. Lead with action and what people do; use the setting and mood only enough to ground the action, never as the focus. Never speak for a character or write dialogue. Reply with the prose only — no tags, no quotes, no preamble."""


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
    ``lead`` folds an explicit cue into the prompt (the branch's narrative direction, or
    a scene-opening hint) so the beat leans into where the player is steering.
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
    system = _SYSTEM_LONG if long else _SYSTEM

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
