"""Input-intent interpreter — read what the player is actually asking for.

The player is the scene's *guide*: a line may narrate the environment, address a
character, **direct** a character to say/do something (puppet — "Beth tells Mei 'I hate
you'"), or direct the whole group ("everyone introduces themselves"). The old loop
treated every line as an opaque stimulus that *some* character answered — so a puppeted
character never performed, and a bystander (or the target) answered the player instead.

This agent classifies the line into a small :class:`TurnIntent` the turn loop acts on: a
**puppeted** character performs the direction **in their own voice** (D1), the
**addressed** character reacts, and a **broadcast** runs every cast member. It is a
structure-only LLM call, roster-constrained, and **best-effort** — a missing/failed/
malformed reply falls back to ``freeform`` (the prior behavior), so a turn never fails
to interpret.

The same call also breaks the line into ``direction_agent`` requirements — the outcomes
the turn owes the player when they are directing rather than conversing. Riding on this
existing call (one extra JSON field) is deliberate: in narrator mode the player's line
*is* the direction, and a second round-trip to re-read the same string would add a whole
LLM call to every turn. POV-mode guidance is a different string and is parsed separately
by :func:`app.agents.direction_agent.parse`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.agents._common import decision_timeout, extract_json, resolve_llm
from app.agents.direction_agent import (
    REQUIREMENTS_RULES,
    REQUIREMENTS_SCHEMA,
    DirectionRequirement,
    resolve_requirements,
)
from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.services import llm
from app.services.assembler import TurnContext

# Interpreting the ask is a cheap structural call — keep the thinking budget low.
INTENT_EFFORT = ReasoningEffort.LOW

_KINDS = {"puppet", "direct", "broadcast", "narration", "freeform"}
_SCOPES = {"all", "some", "none"}

_SYSTEM = f"""You interpret the player's latest line in an interactive story. The player is the guide/narrator — they may narrate the scene, address a character, DIRECT a character to say or do something (puppet), or direct the whole group. Classify the line — STRUCTURE ONLY, never prose.

Return ONLY a JSON object:
{{"kind": "puppet"|"direct"|"broadcast"|"narration"|"freeform",
 "actors": [roster numbers the player is DIRECTING to act/speak],
 "addressed": [roster numbers the player is addressing or targeting],
 "scope": "all"|"some"|"none",
 "directive": "<one short clause: what the player wants to happen>",
 {REQUIREMENTS_SCHEMA}}}

Rules:
- "puppet": the player makes a specific character do/say something (e.g. "Beth tells Mei 'I hate you'"). Put the acting character (Beth) in "actors" and the target (Mei) in "addressed".
- "direct": the player acts/speaks toward a character without puppeting one (e.g. "I glare at Mei"). "addressed" = the target; "actors" = [].
- "broadcast": the player directs the whole group (e.g. "everyone introduces themselves"). Set "scope" = "all".
- "narration": the player sets the scene/mood with no specific target.
- "freeform": anything else.
- Use ONLY the roster numbers given; never invent one. "directive" restates the ask in one plain clause.
{REQUIREMENTS_RULES}
- No prose, no commentary — just the JSON object."""


@dataclass
class TurnIntent:
    """What the player's line is asking for (resolved to character ids)."""

    kind: str = "freeform"
    directed_actors: list[str] = field(default_factory=list)  # puppeted → perform in-voice
    addressed: list[str] = field(default_factory=list)  # targeted → should react
    scope: str = "none"  # "all" → the whole group acts
    directive: str = ""  # a plain restatement of the ask (for the planner)
    # The outcomes this line owes the turn when the player is DIRECTING the scene rather
    # than conversing with it. Empty for an ordinary line — and always ignored under Player
    # POV, where the line is the character's own dialogue and the direction (if any) came
    # from the separate guidance box.
    requirements: list[DirectionRequirement] = field(default_factory=list)


def _freeform(text: str) -> TurnIntent:
    return TurnIntent(kind="freeform", directive=(text or "").strip())


def interpret(
    db: Session, ctx: TurnContext, text: str, *, locked_id: str | None = None
) -> TurnIntent:
    """Classify the player's line into a :class:`TurnIntent` (best-effort → freeform).

    ``locked_id`` is the Player POV character. Under POV the player **is** that character,
    so their line can never be *addressed to* or *puppeting* them — and a roster that still
    listed them let exactly that happen: in the session that prompted this fix, the player
    wrote as Valdar and the intent came back "tell Valdar you want to be inside of him".
    The planner then (correctly) drops the POV character from its own roster, so the only
    character the turn was aimed at was not selectable and the turn ended in silence.
    Removing them from the roster shown here makes that misreading unrepresentable rather
    than merely unlikely.
    """
    if not ctx.cast:
        return _freeform(text)
    try:
        base_url, api_key, model, params = resolve_llm(db)
    except APIError:
        return _freeform(text)

    selectable = [m for m in ctx.cast if m.id != locked_id]
    if not selectable:
        return _freeform(text)
    roster = "\n".join(f"[{i + 1}] {m.name} — {m.role}" for i, m in enumerate(selectable))
    user = f"Roster:\n{roster}\n\nPlayer's line:\n{text}\n\nInterpret it."
    try:
        raw = llm.chat_complete(
            base_url,
            api_key,
            model,
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            params,
            reasoning=INTENT_EFFORT,
            timeout_s=decision_timeout(),
        )
        data = extract_json(raw)
    except APIError:
        return _freeform(text)

    roster_ids = {i + 1: m.id for i, m in enumerate(selectable)}
    kind = str(data.get("kind", "")).lower()
    if kind not in _KINDS:
        kind = "freeform"
    scope = str(data.get("scope", "")).lower()
    if scope not in _SCOPES:
        scope = "none"
    directive = str(data.get("directive", "")).strip() or (text or "").strip()
    return TurnIntent(
        kind=kind,
        directed_actors=_resolve(data.get("actors"), roster_ids),
        addressed=_resolve(data.get("addressed"), roster_ids),
        scope=scope,
        directive=directive,
        requirements=resolve_requirements(data.get("requirements"), roster_ids),
    )


def _resolve(raw: object, roster_ids: dict[int, str]) -> list[str]:
    """Map roster numbers → character ids (roster-constrained, de-duped, order kept)."""
    out: list[str] = []
    for value in raw if isinstance(raw, list) else []:
        number = _as_int(value)
        if number is None:
            continue
        cid = roster_ids.get(number)
        if cid is not None and cid not in out:
            out.append(cid)
    return out


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        m = re.search(r"\d+", value)
        return int(m.group()) if m else None
    return None
