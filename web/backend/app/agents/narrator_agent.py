"""Narrator agent — the optional interstitial beat (Playwright mode only).

This is **the** Narrator: the AI voice that writes third-person prose inside the scene. The
player's own non-POV mode is the *Playwright*, which steers the scene from outside it and
never speaks in it — two different things that shared one word until 2026-08-24.

Narration is a *decoration* on the one POV loop, not a separate engine (D1): in
Playwright mode a short, third-person environmental/transition beat is inserted where a
transition needs it; in POV Mode it is off (environment rides inside a character's
perception instead). Best-effort: a missing/failed LLM yields ``None`` and the turn
simply skips the interstitial.
"""

from __future__ import annotations

from collections.abc import Generator

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


def _build_prompt(
    ctx: TurnContext,
    turn_beats: list[dict],
    *,
    lead: str | None,
    long: bool,
) -> tuple[str, str]:
    """Build the ``(system, user)`` pair for a narration beat.

    Shared by the blocking and streaming paths so the two cannot drift on setting flavor,
    tagged files, the direction cue, or which system prompt a long beat gets.
    """
    setting = ""
    if ctx.setting is not None:
        flavor = ctx.setting.atmosphere or ctx.setting.current_state or ctx.setting.desc or ""
        setting = f"Setting: {ctx.setting.name}{(' — ' + flavor) if flavor else ''}.\n"
    transcript = _recent(ctx, turn_beats)
    # The player's @-tagged files, placed BEFORE the direction cue so the cue stays nearest
    # the ask: the notes ground the prose's facts, the direction still decides its content.
    # (Note the narrator deliberately does NOT take ``ctx.retrieved_lore`` — the gated and
    # the explicit channels are controlled independently.)
    tagged = f"{ctx.tagged_notes.strip()}\n" if ctx.tagged_notes else ""
    lead_line = f"Direction to follow: {lead}\n" if lead else ""
    ask = (
        "Write the narrator's opening/progression passage now."
        if long
        else "Write the narrator's transition beat now."
    )
    # Same placement as the character prompt: the scene's memory sits immediately above the
    # transcript, so it re-anchors on the same turn the window does.
    memory = (
        f"Earlier in this scene (summary):\n{ctx.history_summary}\n\n"
        if ctx.history_summary
        else ""
    )
    user = f"{setting}{tagged}{memory}{lead_line}Recent beats:\n{transcript}\n\n{ask}"
    system = (
        ctx.prompts.get(prompt_registry.NARRATOR_SYSTEM_LONG, _SYSTEM_LONG)
        if long
        else ctx.prompts.get(prompt_registry.NARRATOR_SYSTEM, _SYSTEM)
    )
    return system, user


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
    scene-opening hint, or — under Playwright-guided scenes — the player's scene direction
    plus the specific outcomes THIS beat owes) so the beat leans into where the player is
    steering. The turn engine composes it; this agent just places it above the transcript,
    where it reads as the destination for the prose rather than as text to restate.
    """
    try:
        base_url, api_key, model, params = resolve_llm(db)
    except APIError:
        return None

    system, user = _build_prompt(ctx, turn_beats, lead=lead, long=long)

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


def stream_interstitial(
    db: Session,
    ctx: TurnContext,
    turn_beats: list[dict],
    *,
    lead: str | None = None,
    long: bool = False,
) -> Generator[llm.StreamDelta, None, str | None]:
    """Stream a narration beat; return the finished text, or ``None`` to skip it.

    The streaming sibling of :func:`interstitial`, building the identical prompt. It
    matters most for a scene's FIRST message, which is narrator-led — leaving it blocking
    would mean the very first thing a new player sees is still a blank wait.

    Best-effort in the same way: an unconfigured or failing endpoint yields nothing and
    returns ``None``, and the turn simply carries on without a narrator beat.
    """
    try:
        base_url, api_key, model, params = resolve_llm(db)
    except APIError:
        return None
    system, user = _build_prompt(ctx, turn_beats, lead=lead, long=long)
    try:
        text, _ = yield from llm.chat_complete_stream(
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
            # NOT "Player" — see character_turn_agent._transcript, which carries the full
            # reasoning. 6 of 10 narration beats in the EXP-2026-08-008 run narrated "the
            # player" as if it were a name; "You" fixed that and, under Playwright mode,
            # created the opposite defect by giving the narrator a second person to narrate.
            # Unconditional for the reason character_turn_agent._transcript documents: a
            # `player` beat is only ever a Playwright direction.
            who = "Direction"
        elif cid:
            who = names.get(cid, "Someone")
        else:
            who = "Narrator"
        lines.append(f"{who}: {text}")
    return "\n".join(lines) or "(scene opening)"
