"""Director agent — who reacts this turn, and in what order (structure only).

The Scene-Manager step (the turn-loop plan §4 / §11.2). For the common beat it is
trivial — a directed addressee answers, or a solo cast member speaks — and runs with
**no** LLM call. For a charged/crowded beat with no clear addressee it escalates to a
reasoned, structure-only LLM decision (speaker order, branch flag, beat label),
constrained to the roster. It is **best-effort**: a missing/failed LLM falls back to a
heuristic so a turn never fails to pick a speaker. It emits no prose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agents._common import extract_json, resolve_llm
from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.services import llm
from app.services.assembler import TurnContext

# A who's-up decision is a cheap structural call — keep the thinking budget low.
DIRECTOR_EFFORT = ReasoningEffort.LOW

# Cap reactors per turn (readability + the staleness cascade). The multi-party
# live-queue + re-rank lifts coordination further; this is the per-call ceiling.
_MAX_SPEAKERS = 3

_SYSTEM = """You are the scene director for an interactive story. Decide which characters should react to the latest beat, and in what order — STRUCTURE ONLY, never prose.

Return ONLY a JSON object:
{"speakers": [roster numbers, most-provoked first], "needsBranch": true|false, "beat": "short label"}

Rules:
- Pick the few characters (1-3) with something real to add; the rest stay silent. Not everyone reacts.
- Lead with whoever is most provoked (addressed, threatened, or whose stake just spiked).
- Use only the roster numbers given. "needsBranch" is true only when the player faces a real fork.
- No prose, no commentary — just the JSON object."""


@dataclass
class DirectorDecision:
    """The turn's speaking plan: ordered character ids, branch flag, beat label."""

    speakers: list[str]
    needs_branch: bool
    beat: str


def who_is_up(db: Session, ctx: TurnContext) -> DirectorDecision:
    """Decide the speaking subset + order for this turn (best-effort; never raises)."""
    if not ctx.cast:
        return DirectorDecision([], False, "empty")

    # Fast path 1 — a directed addressee answers.
    if ctx.directed_at:
        addressed = ctx.cast_by_id(ctx.directed_at)
        if addressed is not None:
            return DirectorDecision([addressed.id], False, "addressed")

    # Fast path 2 — a solo cast member always speaks.
    if len(ctx.cast) == 1:
        return DirectorDecision([ctx.cast[0].id], False, "solo")

    # Escalate to a reasoned, roster-constrained decision.
    return _reasoned_decision(db, ctx)


def _reasoned_decision(db: Session, ctx: TurnContext) -> DirectorDecision:
    fallback = DirectorDecision([ctx.cast[0].id], False, "fallback")
    try:
        base_url, api_key, model, params = resolve_llm(db)
    except APIError:
        return fallback  # unconfigured LLM — pick the first cast member, still run the turn

    roster = "\n".join(f"[{i + 1}] {m.name} — {m.role}" for i, m in enumerate(ctx.cast))
    transcript = _recent(ctx)
    user = f"Roster:\n{roster}\n\nRecent beats:\n{transcript}\n\nWho reacts now?"
    try:
        raw = llm.chat_complete(
            base_url,
            api_key,
            model,
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            params,
            reasoning=DIRECTOR_EFFORT,
        )
        data = extract_json(raw)
    except APIError:
        return fallback  # malformed/empty — degrade gracefully

    roster_ids = {i + 1: m.id for i, m in enumerate(ctx.cast)}
    speakers: list[str] = []
    raw_speakers = data.get("speakers", [])
    for num in raw_speakers if isinstance(raw_speakers, list) else []:
        number = _as_int(num)
        if number is None:
            continue
        cid = roster_ids.get(number)
        if cid is not None and cid not in speakers:
            speakers.append(cid)
        if len(speakers) >= _MAX_SPEAKERS:
            break
    if not speakers:
        return fallback
    return DirectorDecision(speakers, bool(data.get("needsBranch", False)), str(data.get("beat", "")))


_RERANK_SYSTEM = """You are the scene director mid-turn. A beat just shifted the room, and some characters have not yet spoken this turn. RE-RANK only those remaining speakers by who is now most provoked to react next — STRUCTURE ONLY, never prose.

Return ONLY a JSON object: {"speakers": [remaining roster numbers, most-provoked first]}

Rules:
- Use ONLY the remaining roster numbers given (never add a character who already spoke or is absent).
- You may drop a remaining speaker who no longer has anything to add; keep the order meaningful.
- No prose, no commentary — just the JSON object."""


def rerank(db: Session, ctx: TurnContext, remaining_ids: list[str], turn_beats: list[dict]) -> list[str]:
    """Re-rank the not-yet-spoken speakers after a shift (best-effort → unchanged order).

    A mid-turn re-consult (§P10 live queue): the whole cast is numbered so the model
    speaks the same roster language as ``who_is_up``; the result is filtered back to the
    still-remaining ids, preserving any the model omits at the tail so no one is lost.
    """
    if len(remaining_ids) <= 1:
        return remaining_ids
    try:
        base_url, api_key, model, params = resolve_llm(db)
    except APIError:
        return remaining_ids

    roster = "\n".join(f"[{i + 1}] {m.name} — {m.role}" for i, m in enumerate(ctx.cast))
    roster_ids = {i + 1: m.id for i, m in enumerate(ctx.cast)}
    remaining_set = set(remaining_ids)
    numbers = ", ".join(str(n) for n, cid in roster_ids.items() if cid in remaining_set)
    transcript = "\n".join(f"{b.get('role')}: {b.get('text', '')}" for b in turn_beats if b.get("text"))
    user = (
        f"Full roster:\n{roster}\n\nRemaining (not yet spoken) numbers: {numbers}\n\n"
        f"This turn so far:\n{transcript}\n\nRe-rank the remaining speakers now."
    )
    try:
        raw = llm.chat_complete(
            base_url,
            api_key,
            model,
            [{"role": "system", "content": _RERANK_SYSTEM}, {"role": "user", "content": user}],
            params,
            reasoning=DIRECTOR_EFFORT,
        )
        data = extract_json(raw)
    except APIError:
        return remaining_ids

    ordered: list[str] = []
    raw_speakers = data.get("speakers", [])
    for num in raw_speakers if isinstance(raw_speakers, list) else []:
        number = _as_int(num)
        if number is None:
            continue
        cid = roster_ids.get(number)
        if cid in remaining_set and cid not in ordered:
            ordered.append(cid)
    # Preserve any remaining speaker the model omitted (never silently drop someone).
    ordered.extend(cid for cid in remaining_ids if cid not in ordered)
    return ordered


_BRANCH_SYSTEM = """You are the scene director. The player faces a fork. Offer 2-4 distinct branch options — STRUCTURE ONLY, no prose narration.

Return ONLY a JSON object:
{"choices": [{"label": "what the player does/says (short)", "outcome": "direction tag: de-escalate | escalate | bribe | probe | retreat | …"}]}

Rules:
- Each option is a real, in-character direction the scene could take next.
- "outcome" is a short narrative-direction tag, never a dice check or stat test.
- Surface only options that fit the current stats/tone (e.g. don't offer a calm option to a furious character).
- No prose, no commentary — just the JSON object."""

# Cap branch options offered per fork.
_MAX_BRANCHES = 4


def propose_branches(db: Session, ctx: TurnContext, turn_beats: list[dict]) -> list[dict]:
    """Generate branch options (label + outcome) for a fork; best-effort → ``[]``."""
    try:
        base_url, api_key, model, params = resolve_llm(db)
    except APIError:
        return []

    roster = "\n".join(f"[{i + 1}] {m.name} — {m.role}" for i, m in enumerate(ctx.cast))
    recent = "\n".join(f"{b.get('role')}: {b.get('text', '')}" for b in turn_beats if b.get("text"))
    user = f"Roster:\n{roster}\n\nThis turn so far:\n{recent}\n\nOffer the player's branch options now."
    try:
        raw = llm.chat_complete(
            base_url,
            api_key,
            model,
            [{"role": "system", "content": _BRANCH_SYSTEM}, {"role": "user", "content": user}],
            params,
            reasoning=DIRECTOR_EFFORT,
        )
        data = extract_json(raw)
    except APIError:
        return []

    raw_choices = data.get("choices", [])
    choices: list[dict] = []
    for item in raw_choices if isinstance(raw_choices, list) else []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        if not label:
            continue
        choices.append({"label": label, "outcome": str(item.get("outcome", "")).strip()})
        if len(choices) >= _MAX_BRANCHES:
            break
    return choices


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        m = re.search(r"\d+", value)
        return int(m.group()) if m else None
    return None


def _recent(ctx: TurnContext, limit: int = 6) -> str:
    names = {m.id: m.name for m in ctx.cast}
    lines: list[str] = []
    for beat in ctx.recent_beats[-limit:]:
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
