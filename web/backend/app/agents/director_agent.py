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

from app.agents import prompt_registry
from app.agents._common import extract_json, resolve_llm
from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.services import llm
from app.services.assembler import CastMember, TurnContext

# A who's-up decision is a cheap structural call — keep the thinking budget low.
DIRECTOR_EFFORT = ReasoningEffort.LOW

# Cap reactors per turn (readability + the staleness cascade). The multi-party
# live-queue + re-rank lifts coordination further; this is the per-call ceiling.
_MAX_SPEAKERS = 3

# Default director prompt text lives in ``prompt_registry`` (single source of truth for
# editable writing prompts); resolved per-turn text rides on ``ctx.prompts``.
_SYSTEM = prompt_registry.default(prompt_registry.DIRECTOR_WHO_IS_UP)


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
            [
                {"role": "system", "content": ctx.prompts.get(prompt_registry.DIRECTOR_WHO_IS_UP, _SYSTEM)},
                {"role": "user", "content": user},
            ],
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


_RERANK_SYSTEM = prompt_registry.default(prompt_registry.DIRECTOR_RERANK)


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
            [
                {"role": "system", "content": ctx.prompts.get(prompt_registry.DIRECTOR_RERANK, _RERANK_SYSTEM)},
                {"role": "user", "content": user},
            ],
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


_BRANCH_SYSTEM = prompt_registry.default(prompt_registry.DIRECTOR_BRANCH)

# Hard cap on branch options offered per fork (the configurable count is clamped to this).
_MAX_BRANCHES = 4


def propose_branches(
    db: Session, ctx: TurnContext, turn_beats: list[dict], count: int = _MAX_BRANCHES
) -> list[dict]:
    """Generate ``count`` situation-based follow-up moves for the general player.

    ``count`` (0–4) is the configured number of follow-up suggestions; ``0`` disables the
    feature (returns ``[]`` with no LLM call). Options are SITUATION-BASED — what happens
    next in the scenario from a general, story-wide perspective, not any one character's
    next spoken line — and are written to match the tone/pace of the player's own recent
    moves (request #1), anchored to what just happened. Best-effort → ``[]``.
    """
    want = max(0, min(count, _MAX_BRANCHES))
    if want == 0:
        return []
    try:
        base_url, api_key, model, params = resolve_llm(db)
    except APIError:
        return []

    roster = "\n".join(f"[{i + 1}] {m.name} — {m.role}" for i, m in enumerate(ctx.cast))
    sequence = _recent_sequence(ctx, turn_beats)
    voice = _player_voice(ctx, turn_beats)
    voice_block = (
        "The player writes their moves like this — match this voice, length, and pace:\n"
        f"{voice}\n\n"
        if voice
        else ""
    )
    user = (
        f"Roster (scene context only — do not write in any of their voices):\n{roster}\n\n"
        # The recent beats IN ORDER (oldest→newest) so the model sees the scene's trajectory,
        # not a single cherry-picked line — the last line is where the story now stands.
        f"The scene so far (oldest to newest — the LAST line is the current moment):\n{sequence}\n\n"
        f"{voice_block}"
        f"Offer EXACTLY {want} distinct situation-based follow-up move(s) that continue the scene "
        "FORWARD from the LAST line above — what happens NEXT, building on what just happened. Do "
        "NOT repeat, undo, or rewind anything already shown above (those events have happened and "
        "cannot be re-offered). Match the player's tone and pace."
    )
    try:
        raw = llm.chat_complete(
            base_url,
            api_key,
            model,
            [
                {"role": "system", "content": ctx.prompts.get(prompt_registry.DIRECTOR_BRANCH, _BRANCH_SYSTEM)},
                {"role": "user", "content": user},
            ],
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
        if len(choices) >= want:
            break
    return choices


_POV_BRANCH_SYSTEM = prompt_registry.default(prompt_registry.DIRECTOR_POV_BRANCH)


def propose_pov_lines(
    db: Session,
    ctx: TurnContext,
    turn_beats: list[dict],
    speaker: CastMember,
    count: int = _MAX_BRANCHES,
) -> list[dict]:
    """Generate ``count`` first-person candidate next lines **in the POV character's voice**.

    The Player-POV counterpart to :func:`propose_branches`: instead of situation-wide moves
    written from a general narrator's perspective, these are lines *this* character
    (``speaker``, the character the player is speaking AS) might say next — grounded in their
    established voice/tone and anchored to the latest beat. They flow into the composer via the
    same ``branch_choices`` → choose → composer path, so no new event type is needed.
    ``count`` (0–4) is the configured suggestion count; ``0`` disables (no LLM call).
    Best-effort → ``[]``.
    """
    want = max(0, min(count, _MAX_BRANCHES))
    if want == 0:
        return []
    try:
        base_url, api_key, model, params = resolve_llm(db)
    except APIError:
        return []

    sequence = _recent_sequence(ctx, turn_beats)
    identity = f"{speaker.name}" + (f" — {speaker.role}" if speaker.role else "")
    voice_bits = [b for b in (speaker.speech, speaker.voice_samples, speaker.disposition) if b]
    voice_block = (
        "This character's voice, manner, and current stance (match it):\n"
        + "\n".join(voice_bits)
        + "\n\n"
        if voice_bits
        else ""
    )
    user = (
        f"The player is speaking AS this character:\n{identity}\n\n"
        f"{voice_block}"
        f"The scene so far (oldest to newest — the LAST line is the current moment):\n{sequence}\n\n"
        f"Offer EXACTLY {want} distinct first-person line(s) that {speaker.name} might say NEXT, "
        "in their own voice, continuing FORWARD from the LAST line above. Do NOT repeat, undo, or "
        "rewind anything already shown. Keep the options distinct in intent."
    )
    try:
        raw = llm.chat_complete(
            base_url,
            api_key,
            model,
            [
                {"role": "system", "content": ctx.prompts.get(prompt_registry.DIRECTOR_POV_BRANCH, _POV_BRANCH_SYSTEM)},
                {"role": "user", "content": user},
            ],
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
        if len(choices) >= want:
            break
    return choices


def _recent_sequence(ctx: TurnContext, turn_beats: list[dict], limit: int = 6) -> str:
    """Render the last ``limit`` beats (committed history + this turn) IN ORDER.

    Follow-up suggestions must CONTINUE from where the scene now stands, so the model needs
    the recent *sequence* — not one cherry-picked line — to read the story's direction. The
    beats are combined chronologically and the newest sits last (recency), with speakers
    named (Player / Narrator / the character's name) so the trajectory is legible. Empty →
    "(scene opening)" so a cold open still gets a sensible cue.
    """
    names = {m.id: m.name for m in ctx.cast}
    lines: list[str] = []
    for beat in [*ctx.recent_beats, *turn_beats][-limit:]:
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
    return "\n".join(lines) if lines else "(scene opening)"


def _player_voice(ctx: TurnContext, turn_beats: list[dict], limit: int = 3) -> str:
    """The player's own recent authored lines (oldest→newest) — the tone/pace to match.

    Suggestions should read like something the player would write (request #1), so we hand
    the model the player's established voice: their most recent ``player`` beats drawn from
    the committed history and this turn (deduped, newest first, capped at ``limit``). Only
    the player's writing is sampled — never a character's line — so the model matches the
    general narrator's register, not any character's voice. Empty when the player has not
    written anything yet.
    """
    lines: list[str] = []
    for beat in reversed([*ctx.recent_beats, *turn_beats]):
        if beat.get("role") != "player":
            continue
        text = str(beat.get("text", "")).strip()
        if text and text not in lines:
            lines.append(text)
        if len(lines) >= limit:
            break
    return "\n".join(f"- {t}" for t in reversed(lines))


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
