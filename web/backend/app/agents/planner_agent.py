"""ReAct turn planner — decide the SINGLE next beat, then re-decide after it happens.

Replaces the old one-shot Director (`director_agent.who_is_up`, capped at 3 speakers,
plus the bolt-on rerank/cascade). The turn loop calls :func:`next_beat` in a
reason→act→observe loop: pick the next beat (a character speaks/acts, the narrator sets
context, or the turn ends), run it, append it to the transcript, then call again with the
updated transcript. This makes the flow dynamic and **unbounded** — "everyone introduces
themselves" keeps choosing the next character who hasn't gone until all have (D2/D3), and
the narrator can fill context *between* speakers regardless of mode.

Structure-only + roster-constrained + **best-effort**: a missing/failed/malformed reply
falls back to a simple heuristic (honor an explicit group/addressed target, else end), so
a turn never stalls. It emits no prose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agents._common import extract_json, resolve_llm
from app.agents.intent_agent import TurnIntent
from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.services import llm
from app.services.assembler import TurnContext

# Deciding one beat is a cheap structural call — keep the thinking budget low.
PLANNER_EFFORT = ReasoningEffort.LOW

_ACTIONS = {"speak", "narrate", "end"}

_SYSTEM = """You are the scene director running one interactive-story turn as a step-by-step loop. Decide the SINGLE next beat given what has happened so far this turn — STRUCTURE ONLY, never prose.

Return ONLY a JSON object:
{"action": "speak"|"narrate"|"end", "actor": <roster number or null>, "addressing": <roster number or null>, "reason": "<short why>", "needsBranch": true|false}

Rules:
- "narrate" is the DEFAULT for carrying the scene: use the narrator to PROGRESS the story to the next beat — narrate what the characters are DOING and push the action forward, especially in an action or tense moment (a fight, a chase, a standoff), following moves through to their consequence. Narration moves the story; lean on it to advance the scene to the point where a character actually has something to react to.
- "speak": character <actor> acts/speaks next, optionally directed at <addressing>. Choose this ONLY once the scene has MOVED FORWARD and this character has a genuine point-of-view reaction, thought, or decision to voice about what is now happening. Do NOT have a character talk when the moment calls for action, or when nothing has changed since they last spoke — that is over-talking. Prefer narrating the action forward, then let a character respond to where it landed.
- "end": the player's direction is satisfied and the exchange is at a natural stopping point.
- SCENE OPENING: if nothing has happened yet this turn AND the player did not direct or address a specific character (and did not address the whole group), OPEN WITH "narrate" to set the scene in motion — do NOT have a character speak first. A character speaks unprompted at a cold open is wrong.
- HONOR THE PLAYER'S DIRECTION. If they told the WHOLE GROUP to do something ("everyone introduces themselves"), keep choosing the next character who has NOT yet taken a beat until every one of them has, THEN end — never stop early.
- Do not repeat a character who already had their beat unless there is a real reason.
- Use ONLY the roster numbers given. "needsBranch" is true only when you end at a genuine fork for the player.
- No prose, no commentary — just the JSON object."""


@dataclass
class BeatDecision:
    """The next beat to run this turn (or ``end``)."""

    action: str  # "speak" | "narrate" | "end"
    actor_id: str | None = None
    addressing_id: str | None = None
    reason: str = ""
    needs_branch: bool = False


def next_beat(
    db: Session,
    ctx: TurnContext,
    intent: TurnIntent,
    turn_beats: list[dict],
    acted: list[str],
    *,
    scene_opening: bool = False,
) -> BeatDecision:
    """Decide the next beat (best-effort; never raises).

    ``scene_opening`` marks the scene's very first beat (no committed history): a cold
    open with no direction should be narrator-led, not a character talking unprompted.
    """
    if not ctx.cast:
        return BeatDecision("end", reason="no cast")
    try:
        base_url, api_key, model, params = resolve_llm(db)
    except APIError:
        return _fallback_beat(ctx, intent, acted, scene_opening=scene_opening)

    roster_ids = {i + 1: m.id for i, m in enumerate(ctx.cast)}
    roster = "\n".join(f"[{i + 1}] {m.name} — {m.role}" for i, m in enumerate(ctx.cast))
    acted_nums = [str(n) for n, cid in roster_ids.items() if cid in set(acted)]
    scope_note = " The player addressed the WHOLE GROUP." if intent.scope == "all" else ""
    opening_note = (
        " This is the SCENE OPENING (nothing has happened yet) — open with a narrator beat unless the player directed a specific character."
        if scene_opening
        else ""
    )
    user = (
        f"Roster:\n{roster}\n\n"
        f"Player's direction: {intent.directive or '(freeform)'}.{scope_note}{opening_note}\n"
        f"Characters who have ALREADY taken a beat this turn (roster numbers): "
        f"{', '.join(acted_nums) or 'none'}\n\n"
        f"This turn so far:\n{_recent(ctx, turn_beats)}\n\n"
        "What is the next beat?"
    )
    try:
        raw = llm.chat_complete(
            base_url,
            api_key,
            model,
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            params,
            reasoning=PLANNER_EFFORT,
        )
        data = extract_json(raw)
    except APIError:
        return _fallback_beat(ctx, intent, acted, scene_opening=scene_opening)

    action = str(data.get("action", "")).lower()
    if action not in _ACTIONS:
        return _fallback_beat(ctx, intent, acted, scene_opening=scene_opening)
    if action == "end":
        return BeatDecision("end", reason=str(data.get("reason", "")), needs_branch=bool(data.get("needsBranch", False)))
    if action == "narrate":
        return BeatDecision("narrate", reason=str(data.get("reason", "")))
    actor_id = roster_ids.get(_as_int(data.get("actor")) or -1)
    if actor_id is None:
        return _fallback_beat(ctx, intent, acted, scene_opening=scene_opening)
    return BeatDecision(
        "speak",
        actor_id=actor_id,
        addressing_id=roster_ids.get(_as_int(data.get("addressing")) or -1),
        reason=str(data.get("reason", "")),
    )


def _fallback_beat(
    ctx: TurnContext,
    intent: TurnIntent,
    acted: list[str],
    *,
    scene_opening: bool = False,
) -> BeatDecision:
    """Model-free next beat: honor an explicit group/addressed target, else end.

    Keeps the loop sensible offline (and in tests): a broadcast walks the whole cast, an
    addressed character reacts once, freeform input mid-scene gets one responder. On a
    cold ``scene_opening`` with no direction, though, nobody is forced to speak — the
    narrator opens the scene (handled by the engine) and the turn ends."""
    acted_set = set(acted)
    if intent.scope == "all":
        for m in ctx.cast:
            if m.id not in acted_set:
                return BeatDecision("speak", actor_id=m.id, reason="next in the group")
        return BeatDecision("end", reason="everyone has spoken")
    for cid in intent.addressed:
        if cid not in acted_set and ctx.cast_by_id(cid) is not None:
            return BeatDecision("speak", actor_id=cid, reason="addressed")
    if not acted and not scene_opening:  # freeform mid-scene — one character responds
        return BeatDecision("speak", actor_id=ctx.cast[0].id, reason="responds")
    return BeatDecision("end", reason="direction satisfied")


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        m = re.search(r"\d+", value)
        return int(m.group()) if m else None
    return None


def _recent(ctx: TurnContext, turn_beats: list[dict], limit: int = 10) -> str:
    names = {m.id: m.name for m in ctx.cast}
    lines: list[str] = []
    for beat in turn_beats[-limit:]:
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
    return "\n".join(lines) or "(nothing yet)"
