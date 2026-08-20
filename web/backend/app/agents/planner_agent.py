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

from app.agents import prompt_registry
from app.agents._common import decision_timeout, extract_json, resolve_llm
from app.agents.direction_agent import SceneDirection
from app.agents.intent_agent import TurnIntent
from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.services import llm
from app.services.assembler import TurnContext

# Deciding one beat is a cheap structural call — keep the thinking budget low.
PLANNER_EFFORT = ReasoningEffort.LOW

_ACTIONS = {"speak", "narrate", "exit", "end"}
# The beat's REGISTER — the planner's read of how the situation stands right now, on one
# axis from banter to life-and-death. It is the situational-adaptation signal the character
# prompt was previously asking each speaker to infer for itself while its own voice samples
# argued the other way. Whitelisted on parse; anything else (or a fallback beat) yields
# ``None``, and every consumer must then behave exactly as it did before registers existed.
_REGISTERS = ("light", "neutral", "tense", "grave")
# The presence transitions the planner may trigger via an "exit" beat (never "present" —
# a re-entry is a player/manual action, not something the planner decides mid-scene).
_EXIT_STATUSES = {"unconscious", "departed", "left", "dead"}

# Default planner prompt text lives in ``prompt_registry`` (single source of truth for
# editable writing prompts); resolved per-turn text rides on ``ctx.prompts``.
_SYSTEM = prompt_registry.default(prompt_registry.PLANNER_SYSTEM)


@dataclass
class BeatDecision:
    """The next beat to run this turn (or ``end``)."""

    action: str  # "speak" | "narrate" | "exit" | "end"
    actor_id: str | None = None
    addressing_id: str | None = None
    reason: str = ""
    needs_branch: bool = False
    # For an "exit" beat: the presence status to transition <actor> into (Scene Presence
    # & Director Actions). One of _EXIT_STATUSES; ``None`` for every other action.
    status: str | None = None
    # The planner's read of the moment (one of ``_REGISTERS``), and the concrete thing at
    # risk in it. ``register`` is ``None`` whenever the planner did not run or replied with
    # something unrecognized — consumers then fall back to their pre-register behavior.
    register: str | None = None
    stakes: str = ""


def next_beat(
    db: Session,
    ctx: TurnContext,
    intent: TurnIntent,
    turn_beats: list[dict],
    acted: list[str],
    *,
    scene_opening: bool = False,
    locked_id: str | None = None,
    direction: SceneDirection | None = None,
    remaining_beats: int | None = None,
) -> BeatDecision:
    """Decide the next beat (best-effort; never raises).

    ``scene_opening`` marks the scene's very first beat (no committed history): a cold
    open with no direction should be narrator-led, not a character talking unprompted.

    ``locked_id`` is the Player POV character id (when set): it is dropped from the
    selectable roster so the AI never voices the character the player is speaking as —
    the loop then ends on its own once the remaining cast is done reacting.

    ``direction`` is the player's scene direction (Narrator-Guided Scenes) and
    ``remaining_beats`` how many beats of the scene's cap are left. The outstanding
    requirements are shown as work the turn still owes, so the planner paces them across
    the beats it has. It may still choose freely — the engine takes the schedule out of its
    hands (``direction_agent.schedule``) only once the budget is as tight as the direction
    is long, so a satisfied direction is never left to chance.
    """
    if not ctx.cast:
        return BeatDecision("end", reason="no cast")
    # Only PRESENT characters are selectable; a dead/departed/unconscious one stays in the
    # cast for context but never appears on the roster, so the planner can't pick them. The
    # POV character (``locked_id``) is likewise removed — the player voices them.
    present = [m for m in ctx.cast if m.is_present and m.id != locked_id]
    if not present:
        return BeatDecision("end", reason="no one present")
    try:
        base_url, api_key, model, params = resolve_llm(db)
    except APIError:
        return _fallback_beat(
            ctx, intent, acted, scene_opening=scene_opening, locked_id=locked_id,
            direction=direction,
        )

    roster_ids = {i + 1: m.id for i, m in enumerate(present)}
    roster = "\n".join(f"[{i + 1}] {m.name} — {m.role}" for i, m in enumerate(present))
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
        f"{_owed(direction, roster_ids, remaining_beats)}"
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
            [
                {"role": "system", "content": ctx.prompts.get(prompt_registry.PLANNER_SYSTEM, _SYSTEM)},
                {"role": "user", "content": user},
            ],
            params,
            reasoning=PLANNER_EFFORT,
            timeout_s=decision_timeout(),
        )
        data = extract_json(raw)
    except APIError:
        return _fallback_beat(
            ctx, intent, acted, scene_opening=scene_opening, locked_id=locked_id,
            direction=direction,
        )

    action = str(data.get("action", "")).lower()
    if action not in _ACTIONS:
        return _fallback_beat(
            ctx, intent, acted, scene_opening=scene_opening, locked_id=locked_id,
            direction=direction,
        )
    # The read of the moment rides on every action (it describes the situation, not the
    # beat), so parse it once up front. An unrecognized value degrades to None rather than
    # reaching the character prompt as noise.
    register = str(data.get("register", "")).strip().lower() or None
    if register not in _REGISTERS:
        register = None
    stakes = str(data.get("stakes", "") or "").strip()
    if action == "end":
        return BeatDecision(
            "end", reason=str(data.get("reason", "")),
            needs_branch=bool(data.get("needsBranch", False)),
            register=register, stakes=stakes,
        )
    if action == "narrate":
        return BeatDecision(
            "narrate", reason=str(data.get("reason", "")), register=register, stakes=stakes
        )
    if action == "exit":
        actor_id = roster_ids.get(_as_int(data.get("actor")) or -1)
        status = str(data.get("status", "")).strip().lower()
        if actor_id is None or status not in _EXIT_STATUSES:
            # Malformed exit (no valid target/status) → don't guess a removal; fall back.
            return _fallback_beat(
                ctx, intent, acted, scene_opening=scene_opening, locked_id=locked_id,
                direction=direction,
            )
        return BeatDecision(
            "exit", actor_id=actor_id, status=status, reason=str(data.get("reason", "")),
            register=register, stakes=stakes,
        )
    actor_id = roster_ids.get(_as_int(data.get("actor")) or -1)
    if actor_id is None:
        return _fallback_beat(
            ctx, intent, acted, scene_opening=scene_opening, locked_id=locked_id,
            direction=direction,
        )
    return BeatDecision(
        "speak",
        actor_id=actor_id,
        addressing_id=roster_ids.get(_as_int(data.get("addressing")) or -1),
        reason=str(data.get("reason", "")),
        register=register,
        stakes=stakes,
    )


def _fallback_beat(
    ctx: TurnContext,
    intent: TurnIntent,
    acted: list[str],
    *,
    scene_opening: bool = False,
    locked_id: str | None = None,
    direction: SceneDirection | None = None,
) -> BeatDecision:
    """Model-free next beat: honor an explicit group/addressed target, else end.

    Keeps the loop sensible offline (and in tests): a broadcast walks the whole cast, an
    addressed character reacts once, freeform input mid-scene gets one responder. On a
    cold ``scene_opening`` with no direction, though, nobody is forced to speak — the
    narrator opens the scene (handled by the engine) and the turn ends. ``locked_id``
    (the Player POV character) is never selectable, mirroring :func:`next_beat`.

    An outstanding ``direction`` outranks all of that: what the player asked for is owed
    whether or not the planner call succeeded, so the next unsatisfied requirement picks
    the beat (its owner speaks; a narrator-owned one narrates)."""
    acted_set = set(acted)
    present = [m for m in ctx.cast if m.is_present and m.id != locked_id]  # only selectable
    if not present:
        return BeatDecision("end", reason="no one present")
    for req in direction.outstanding() if direction else []:
        if req.actor_id is None:
            return BeatDecision("narrate", reason="the direction still owes this")
        member = ctx.cast_by_id(req.actor_id)
        if req.actor_id != locked_id and member is not None and member.is_present:
            return BeatDecision("speak", actor_id=req.actor_id, reason="the direction names them")
    if intent.scope == "all":
        for m in present:
            if m.id not in acted_set:
                return BeatDecision("speak", actor_id=m.id, reason="next in the group")
        return BeatDecision("end", reason="everyone has spoken")
    for cid in intent.addressed:
        member = ctx.cast_by_id(cid)
        if cid != locked_id and cid not in acted_set and member is not None and member.is_present:
            return BeatDecision("speak", actor_id=cid, reason="addressed")
    if not acted and not scene_opening:  # freeform mid-scene — one character responds
        return BeatDecision("speak", actor_id=present[0].id, reason="responds")
    return BeatDecision("end", reason="direction satisfied")


def _owed(
    direction: SceneDirection | None,
    roster_ids: dict[int, str],
    remaining_beats: int | None,
) -> str:
    """Render what the player's direction still owes, plus the beats left to deliver it.

    Empty string when there is no direction — the prompt is then byte-identical to the
    pre-direction one, so an ordinary conversational turn is unchanged.
    """
    if direction is None or not direction.active:
        return ""
    outstanding = direction.outstanding()
    if not outstanding:
        return "The player's direction has been fully delivered this turn.\n"
    by_id = {cid: n for n, cid in roster_ids.items()}
    lines = []
    for req in outstanding:
        number = by_id.get(req.actor_id or "")
        who = f"[{number}]" if number else "narrator"
        lines.append(f"  - {who}: {req.text}")
    budget = (
        f"You have {remaining_beats} beat(s) left in this turn — everything above must "
        "happen within them.\n"
        if remaining_beats is not None
        else ""
    )
    return (
        "The player DIRECTED this scene. Still to deliver, in this order:\n"
        + "\n".join(lines)
        + "\n"
        + budget
    )


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
