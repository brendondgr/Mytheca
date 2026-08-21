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

**One call, several beats.** EXP-2026-08-005 measured this agent at 41 % of all turn
time — not because its prompt is large (it carries only this turn's beats) but because it
ran once per beat, three to six times a turn at ~4 s each. :func:`plan_beats` asks for the
next few beats in a single call and the engine executes them, re-planning when the plan
runs out or when reality diverges from it (a character exits, a requirement is delivered,
the budget tightens). :func:`next_beat` is the one-beat wrapper and keeps the original
contract for callers that genuinely want a single decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.agents import prompt_registry
from app.agents._common import decision_timeout, extract_json, resolve_llm
from app.agents.direction_agent import SceneDirection
from app.agents.intent_agent import TurnIntent
from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.services import llm
from app.services.assembler import TurnContext

# Deciding who is up next runs after EVERY beat, so it is paid once per beat and the
# player feels it directly. It wants a quick read of the room, not deliberation — the
# judgement is "who has something to say about what just happened", which a person makes
# instinctually. QUICK (128 tokens) is deliberately below LOW.
PLANNER_EFFORT = ReasoningEffort.QUICK

_ACTIONS = {"speak", "narrate", "exit", "end", "ask"}
# How many options may ride with a clarifying question. The player can always ignore
# them and type their own answer, so this bounds the UI, not the player.
_MAX_ASK_OPTIONS = 4
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

    action: str  # "speak" | "narrate" | "exit" | "end" | "ask"
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
    # For an "ask" beat: the question to put to the player, and up to
    # :data:`_MAX_ASK_OPTIONS` short answers to offer alongside it. ``question`` is
    # required — an "ask" without one is malformed, not a beat with a blank question.
    question: str = ""
    options: list[str] = field(default_factory=list)


def plan_beats(
    db: Session,
    ctx: TurnContext,
    intent: TurnIntent,
    turn_beats: list[dict],
    acted: list[str],
    *,
    lookahead: int = 1,
    scene_opening: bool = False,
    locked_id: str | None = None,
    direction: SceneDirection | None = None,
    remaining_beats: int | None = None,
    may_ask: bool = False,
) -> list[BeatDecision]:
    """Decide the next ``lookahead`` beats in ONE call (best-effort; never raises).

    Returns at least one decision. The list is truncated at the first ``end`` — beats
    planned after the turn stops are meaningless — and every entry is roster-checked, so
    the caller still has to re-validate against presence, which can change mid-turn.

    A ``lookahead`` of 1 reproduces the original single-beat behaviour exactly, including
    the request shape, so an operator who has overridden the planner prompt is unaffected.
    Above 1 the multi-beat contract is appended to the **user** message rather than the
    system one, so it survives a customised system prompt.

    ``may_ask`` opens the ``ask`` action — stop and put a question to the player instead of
    guessing where the story goes. The caller owns that permission because the conditions
    for it are the engine's (nothing has happened this turn, no direction is outstanding,
    the previous turn did not already ask). An ``ask`` returned without it is dropped along
    with everything planned after it: a question the engine cannot deliver is worse than a
    guess. It may also only be the FIRST beat of a plan — a question that arrives after two
    beats have already committed the scene is answering nothing.

    The trade this makes is honest and worth stating: a beat planned three ahead reads a
    moment that has not happened yet, so its ``register`` is a prediction. That is why the
    engine re-plans on divergence instead of executing a whole turn blind.
    """
    if not ctx.cast:
        return [BeatDecision("end", reason="no cast")]
    present = [m for m in ctx.cast if m.is_present and m.id != locked_id]
    if not present:
        return [BeatDecision("end", reason="no one present")]
    try:
        base_url, api_key, model, params = resolve_llm(db)
    except APIError:
        return [_fallback_beat(
            ctx, intent, acted, scene_opening=scene_opening, locked_id=locked_id,
            direction=direction,
        )]

    roster_ids = {i + 1: m.id for i, m in enumerate(present)}
    want = max(1, min(int(lookahead), remaining_beats if remaining_beats else int(lookahead)))
    user = _plan_prompt(
        ctx, intent, turn_beats, acted, roster_ids,
        scene_opening=scene_opening, direction=direction, remaining_beats=remaining_beats,
        want=want, may_ask=may_ask,
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
        return [_fallback_beat(
            ctx, intent, acted, scene_opening=scene_opening, locked_id=locked_id,
            direction=direction,
        )]

    rows = data.get("beats")
    if not isinstance(rows, list) or not rows:
        rows = [data]  # a single-object reply, which is what lookahead=1 asks for
    decisions: list[BeatDecision] = []
    for row in rows[:want]:
        if not isinstance(row, dict):
            continue
        decision = _decision_from(row, roster_ids)
        if decision is None:
            break  # a malformed entry invalidates everything planned after it
        if decision.action == "ask" and (not may_ask or decisions):
            break  # not allowed, or not first — and nothing planned after it still applies
        decisions.append(decision)
        if decision.action in ("end", "ask"):
            break
    if not decisions:
        return [_fallback_beat(
            ctx, intent, acted, scene_opening=scene_opening, locked_id=locked_id,
            direction=direction,
        )]
    return decisions


def _decision_from(data: dict, roster_ids: dict[int, str]) -> BeatDecision | None:
    """Parse ONE planned beat; ``None`` when it is malformed or names nobody real."""
    action = str(data.get("action", "")).lower()
    if action not in _ACTIONS:
        return None
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
    if action == "ask":
        question = str(data.get("question", "") or "").strip()
        if not question:
            return None  # an "ask" with nothing to ask is malformed, not a blank question
        raw_options = data.get("options")
        options = [
            str(o).strip()
            for o in (raw_options if isinstance(raw_options, list) else [])
            if str(o).strip()
        ][:_MAX_ASK_OPTIONS]
        return BeatDecision(
            "ask", question=question, options=options, reason=str(data.get("reason", "")),
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
            return None  # don't guess a removal
        return BeatDecision(
            "exit", actor_id=actor_id, status=status, reason=str(data.get("reason", "")),
            register=register, stakes=stakes,
        )
    actor_id = roster_ids.get(_as_int(data.get("actor")) or -1)
    if actor_id is None:
        return None
    return BeatDecision(
        "speak",
        actor_id=actor_id,
        addressing_id=roster_ids.get(_as_int(data.get("addressing")) or -1),
        reason=str(data.get("reason", "")),
        register=register,
        stakes=stakes,
    )


def _plan_prompt(
    ctx: TurnContext,
    intent: TurnIntent,
    turn_beats: list[dict],
    acted: list[str],
    roster_ids: dict[int, str],
    *,
    scene_opening: bool,
    direction: SceneDirection | None,
    remaining_beats: int | None,
    want: int,
    may_ask: bool = False,
) -> str:
    """The planner's user message. Byte-identical to the pre-lookahead one when ``want`` is 1.

    The ``ask`` contract rides here rather than in the system prompt for two reasons: the
    system message is byte-identical across the turn's calls and is what an inference
    server's prefix cache keys on, and an operator who has overridden the planner prompt
    still gets the action.
    """
    roster = "\n".join(f"[{n}] {ctx.cast_by_id(cid).name} — {ctx.cast_by_id(cid).role}"  # type: ignore[union-attr]
                       for n, cid in roster_ids.items())
    acted_nums = [str(n) for n, cid in roster_ids.items() if cid in set(acted)]
    scope_note = " The player addressed the WHOLE GROUP." if intent.scope == "all" else ""
    opening_note = (
        " This is the SCENE OPENING (nothing has happened yet) — open with a narrator beat unless the player directed a specific character."
        if scene_opening
        else ""
    )
    ask = (
        "What is the next beat?"
        if want == 1
        else (
            f"Plan the next {want} beats, in order. Return "
            '{"beats": [<beat>, <beat>, ...]} where each <beat> is the JSON object '
            "described above. Stop the list early — with an \"end\" beat, or simply "
            "fewer entries — if the turn should finish sooner. Judge each beat from the "
            "situation as it will stand after the ones you planned before it."
        )
    )
    ask_note = (
        '\n\nIf — and only if — you genuinely cannot tell where the player wants this to go, '
        'you may instead return {"action": "ask", "question": "<one short question, in the '
        'story\'s voice>", "options": ["<a short answer>", "<another>"], "register": "...", '
        '"stakes": "..."} to put the question to them and stop the turn there. Ask only when '
        "the line is genuinely open — two or more real directions and no way to choose — never "
        "to check a detail you could simply decide, and never when the scene has an obvious "
        "next move. Guessing well is the job; asking is for when there is nothing to guess from."
        if may_ask
        else ""
    )
    return (
        f"Roster:\n{roster}\n\n"
        f"Player's direction: {intent.directive or '(freeform)'}.{scope_note}{opening_note}\n"
        f"{_owed(direction, roster_ids, remaining_beats)}"
        f"Characters who have ALREADY taken a beat this turn (roster numbers): "
        f"{', '.join(acted_nums) or 'none'}\n\n"
        f"This turn so far:\n{_recent(ctx, turn_beats)}\n\n"
        f"{ask}{ask_note}"
    )


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
    may_ask: bool = False,
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
    return plan_beats(
        db, ctx, intent, turn_beats, acted, lookahead=1,
        scene_opening=scene_opening, locked_id=locked_id, direction=direction,
        remaining_beats=remaining_beats, may_ask=may_ask,
    )[0]


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
    # The POV character is pre-marked as having acted so a broadcast never re-selects the
    # character the player voices. That is NOT the same as "the turn has been answered", and
    # conflating the two is what ended turns 8 and 9 of the ps_0bf9ddc13b session in silence:
    # under POV `acted` is never empty, so the "somebody responds" last resort below could
    # never fire. Only beats taken by a selectable character count as an answer.
    acted_set = {cid for cid in acted if cid != locked_id}
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
    if not acted_set and not scene_opening:  # freeform mid-scene — one character responds
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
